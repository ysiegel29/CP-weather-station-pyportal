''' Will display on PyPortal CURRENT temperature, humidity, wind and time as well as FORECAST bar chart
requires secrets.py with wifi connection details, openwetaher and adafruitIO keys.
'''

import board
import displayio
import simpleio
import analogio
import busio
import time
import rtc
import gc
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_requests as requests
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

try:
    from secrets import secrets
except ImportError:
    print('Secrets key such as WIFI are kept in secrets.py, please add them there!')
    raise


#############################################
# SETTINGS                                  #
#############################################

WEATHER_LOCATION = 2988507 # 5128581 = NY, 2988507 = Paris
TZ_offset = 0 # Time difference between WEATHER_LOCATION and GMT

sun_min = 0     # %
sun_max = 100   # %
temp_min = 0    # Celsius
temp_max = 30   # Celsius
hum_min = 30    # %
hum_max = 100   # %
rain_min = 0    # mm
rain_max = 5    # mm
wind_min = 0    # km/h
wind_max = 30   # km/h

Forecast_nb = 16 # 16 * 3 hours = 2 days
update_freq = 15 # number of seconds between update cycle in infinite loop
displayed_time_update_freq = 60 # number of seconds between displayed time update
weather_update_freq = 300 # number of seconds between weather (and internet time) API requests
attempts = 10  # Number of attempts to retry each request before raising error
error_delay = 10 # Number of seconds to wait before retrying after error

cwd = ('/'+__file__).rsplit('/', 1)[0]  # the current working directory (where this file is)

small_font = bitmap_font.load_font(cwd+'/fonts/mono-bold-8.bdf')
large_font = bitmap_font.load_font(cwd+'/fonts/Arial-Bold-24.bdf')
text_color = 0xffffff

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)


#############################################
# CONNECT TO WIFI                           #
#############################################
print('-'*40)
print('Connecting to WIFI...')
print('-'*40, '\n')

def connect_to_wifi():
    while not esp.is_connected:
        try:
            time.sleep(1)
            esp.connect_AP(secrets['ssid'], secrets['password'])
        except RuntimeError as e:
            print('Could not connect to WIFI, retrying: ', e)
            continue
    print('Connected to', str(esp.ssid, 'utf-8'), '\tRSSI:', esp.rssi, '   IP address is', esp.pretty_ip(esp.ip_address), '\n')
connect_to_wifi()
if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print('\nPYPORTAL found and in idle mode')

requests.set_socket(socket, esp)


#############################################
# CREATE DISPLAY SETUP                      #
#############################################
print('-'*40)
print('Creating DISPLAY...')
print('-'*40, '\n')

display = board.DISPLAY
light = analogio.AnalogIn(board.LIGHT)

board.DISPLAY.brightness = 1
HEIGHT = display.height
WIDTH = display.width
group = displayio.Group(max_size=10)

##### BAR CHART LAYER ##### 0
BC_bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(9)
palette[0] = 0x000000  # BLACK
palette[1] = 0x0000ff  # BLUE RAIN
palette[2] = 0xFFFF00  # YELLOW SUN
palette[4] = 0x90A9D4  # LIGHT BLUE HUMIDITY
palette[5] = 0x858585  # GREY WIND
palette[6] = 0xFC538A  # ROSE TEMP
palette[7] = 0xffffff  # WHITE
palette[8] = 0xFF0000  # ROUGE
BC_tile_grid = displayio.TileGrid(BC_bitmap, pixel_shader=palette)

group.append(BC_tile_grid)

##### TEMPERATURE LAYER ##### 1
text_temp = ' '
TEMP_text_area = label.Label(large_font, text=text_temp, color=text_color)
group.append(TEMP_text_area)

##### HUMIDITY LAYER ##### 2
text_hum = ' '
HUM_text_area = label.Label(large_font, text=text_hum, color=text_color)
group.append(HUM_text_area)

##### WIND LAYER ##### 3
text_wind = ' '
WIND_text_area = label.Label(large_font, text=text_wind, color=text_color)
group.append(WIND_text_area)

##### TIME LAYER ##### 4
text_time = ' '
TIME_text_area = label.Label(large_font, text=text_time, color=text_color)
group.append(TIME_text_area)

##### SUN SCALE LAYER ##### 5
text_sun_scale = str(sun_max) + '\n' + str(sun_min)
SUN_SCALE_text_area = label.Label(small_font, text=text_sun_scale, color=text_color)
SUN_SCALE_text_area.x = 150
SUN_SCALE_text_area.y = 29
group.append(SUN_SCALE_text_area)

##### TEMP SCALE LAYER ##### 6
text_temp_scale = str(temp_max) + '\n' + str(temp_min)
TEMP_SCALE_text_area = label.Label(small_font, text=text_temp_scale, color=text_color)
TEMP_SCALE_text_area.x = 150
TEMP_SCALE_text_area.y = 75
group.append(TEMP_SCALE_text_area)

##### HUMIDITY SCALE LAYER ##### 7
text_hum_scale = str(hum_max) + '\n' + str(hum_min)
HUM_SCALE_text_area = label.Label(small_font, text=text_hum_scale, color=text_color)
HUM_SCALE_text_area.x = 150
HUM_SCALE_text_area.y = 124
group.append(HUM_SCALE_text_area)

##### RAIN SCALE LAYER ##### 8
text_rain_scale = str(rain_max) + '\n' + str(rain_min)
RAIN_SCALE_text_area = label.Label(small_font, text=text_rain_scale, color=text_color)
RAIN_SCALE_text_area.x = 150
RAIN_SCALE_text_area.y = 173
group.append(RAIN_SCALE_text_area)

##### WIND SCALE LAYER ##### 9
text_wind_scale = str(wind_max) + '\n' + str(wind_min)
WIND_SCALE_text_area = label.Label(small_font, text=text_wind_scale, color=text_color)
WIND_SCALE_text_area.x = 150
WIND_SCALE_text_area.y = 219
group.append(WIND_SCALE_text_area)

print('DISPLAY created succesfully\n')


#############################################
# FUNCTIONS                                 #
#############################################

def TZ(mytime): # Add TZ_offset to provided time
    if mytime + TZ_offset > 24:
        mytime = mytime + TZ_offset - 24
    else:
        mytime = mytime + TZ_offset
    return mytime

def update_updatebar(percent): # draw a line at the top for given percent
    end_x = max(0, int(min(WIDTH, WIDTH * percent/100)))
    for x in range(0, end_x):
        BC_bitmap[x, 1] = 1 # blue
    for x in range(end_x, WIDTH):
        BC_bitmap[x, 1] = 0 # black

def draw_day_line(bottom_left, top_right): # Draw a yellow dotted line at Noon (ie 3h after 9am) and a pink line at Midnight (ie 3h after 9pm)
    x_max = top_right[0]
    x_min = bottom_left[0]
    bar_width = int((top_right[0] - bottom_left[0]) / Forecast_nb)

    for forecast in range(0, Forecast_nb - 1):
        if TZ(forecast_array[forecast][2].tm_hour) == 21:
            for y in range(2,HEIGHT):
                BC_bitmap[x_min + (1+forecast)*bar_width, y] = 6
        if TZ(forecast_array[forecast][2].tm_hour) == 9:
            for y in range(2,HEIGHT):
                if (y % 5) == 0:
                    BC_bitmap[x_min + (1+forecast)*bar_width, y] = 2


def draw_bar_chart(UI_index, UI_min, UI_max, bottom_left, top_right, color): # Draw bar chart for specified UI, with given scale, at given position, with specified color
    y_min = top_right[1]
    y_max = bottom_left[1]
    bar_width = int((top_right[0] - bottom_left[0]) / Forecast_nb)

    for forecast in range(0, Forecast_nb - 1):
        UI = forecast_array[forecast][UI_index]

        # add a min level of SUN to identify days and nights
        if UI_index == 6: # add a min level of sun to identify days and nights
            y_bar = min(simpleio.map_range(UI, UI_min, UI_max, y_max, y_min), y_max - 2)
            # print(TZ(forecast_array[forecast][2].tm_hour), TZ(time.localtime(SUNRISE).tm_hour), TZ(time.localtime(SUNSET).tm_hour),UI_index == 6 and not((TZ(forecast_array[forecast][2].tm_hour) > TZ(time.localtime(SUNRISE).tm_hour)) and (TZ(forecast_array[forecast][2].tm_hour) < TZ(time.localtime(SUNSET).tm_hour))))
        else:
            y_bar = simpleio.map_range(UI, UI_min, UI_max, y_max, y_min)

        # If UI_index is SUN, and if forecast time is after SUNRISE and before SUNSET, set color to yelow
        if (UI_index == 6) and not((TZ(forecast_array[forecast][2].tm_hour) > TZ(time.localtime(SUNRISE).tm_hour)) and (TZ(forecast_array[forecast][2].tm_hour) < TZ(time.localtime(SUNSET).tm_hour))):
            color_bis = 5
        else:
            color_bis = color

        for x in range(max(0, int(bottom_left[0]+forecast*bar_width + 1)), min(WIDTH-1, bottom_left[0]+(1+forecast)*bar_width)):
            for y in range(max(y_min, int(y_bar), 0), min(HEIGHT-1, y_max)):
                BC_bitmap[x, y] = color_bis


def update_displayed_time(): # update DISPLAYED time on screen
    print('-'*40)
    print('Updating DISPLAYED TIME...')
    print('-'*40, '\n')

    try:
        mytime = time.localtime(time.time())
        (year, month, day, hour, minute, second, wday, yday, isdst) = mytime
        text_time = '{:02.0f}'.format(hour)+':'+'{:02.0f}'.format(minute) # +':'+'{:02.0f}'.format(second)
        # print('{:02.0f}'.format(hour)+':'+'{:02.0f}'.format(minute) +':'+'{:02.0f}'.format(second))
        TIME_text_area = label.Label(large_font, text=text_time, color=text_color)
        TIME_text_area.x = 28
        TIME_text_area.y = 30
        group[4] = TIME_text_area
        print('DISPLAYED TIME updated succesfully at: ', '{:02.0f}'.format(hour)+':'+'{:02.0f}'.format(minute) +':'+'{:02.0f}'.format(second), '\n')
    except RuntimeError as e:
        print('/nSome error occured updating DISPLAYED TIME! ', e)


def update_internet_time(): # Get INTERNET TIME from adafruit server
    print('-'*40)
    print('Updating TIME from internet...')
    print('-'*40, '\n')

    global location
    internet_time_update_try_count = 0
    time_response = None

    TIME_SERVICE = 'https://io.adafruit.com/api/v2/%s/integrations/time/strftime?x-aio-key=%s'
    TIME_SERVICE_STRFTIME = '&fmt=%25Y-%25m-%25d+%25H%3A%25M%3A%25S.%25L+%25j+%25u+%25z+%25Z'

    api_url = None
    try:
        aio_username = secrets['aio_username']
        aio_key = secrets['aio_key']
        location = secrets['timezone']
    except KeyError:
        raise KeyError("\nOur time service requires a login/password to rate-limit. Please register for a free adafruit.io account and place the user/key in your secrets file under 'aio_username' and 'aio_key'")

    if location:
        print('Updating TIME from internet based on timezone ', location, '...')
        api_url = (TIME_SERVICE + '&tz=%s') % (aio_username, aio_key, location)
    else:
        print('Updating TIME based on IP address')
        api_url = TIME_SERVICE % (aio_username, aio_key)
    api_url += TIME_SERVICE_STRFTIME

    while not time_response:
        try:
            time_response = requests.get(api_url, timeout=10)

            if esp._debug:
                print('Time request: ', api_url)
                print('Time reply: ', time_response.text)
            print('Time reply: ', time_response.text, '\n')
            times = time_response.text.split(' ')
            the_date = times[0]
            the_time = times[1]
            year_day = int(times[2])
            week_day = int(times[3])
            is_dst = None
        except KeyError:
            raise KeyError("Was unable to update the time, try setting secrets['timezone'] according to http://worldtimeapi.org/timezones\n")

        except Exception as error:
            print('Updating time attempt ', internet_time_update_try_count, '/', attempts, ' failed. Retrying...', error)
            esp.reset()
            connect_to_wifi()
            time.sleep(error_delay)
            if internet_time_update_try_count >= attempts:
                raise Exception('Was unable to update time from internet ', attempts, ' times')
            continue

    year, month, mday = [int(x) for x in the_date.split('-')]
    the_time = the_time.split('.')[0]
    hours, minutes, seconds = [int(x) for x in the_time.split(':')]
    now_struct = time.struct_time((year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst))
    rtc.RTC().datetime = now_struct
    time_response.close()
    time_response = None

def update_current_weather(): # update CURRENT wheather
    print('-'*40)
    print('Updating CURRENT weather...')
    print('-'*40, '\n')

    global SUNRISE, SUNSET
    current_try_count = 0
    json_weather_data_1_response = None

    while not json_weather_data_1_response:
        try:
            current_try_count += 1

            print('CURRENT WEATHER update attempt ', current_try_count, '/', attempts, '\n')
            print(CURRENT_WEATHER_DATA_SOURCE_1)
            json_weather_data_1_response = requests.get(CURRENT_WEATHER_DATA_SOURCE_1, timeout=10)
            json_weather_data_1 = json_weather_data_1_response.json() # JSON 1

            weather_1 = json_weather_data_1['weather'][0]['description']
            temperature_1 = '{:.1f}'.format(json_weather_data_1['main']['temp'])
            humidity_1 = '{:.0f}'.format(json_weather_data_1['main']['humidity'])
            wind_1 = '{:.0f}'.format(json_weather_data_1['wind']['speed'])
            SUNRISE = json_weather_data_1['sys']['sunrise']
            SUNSET = json_weather_data_1['sys']['sunset']

            text_temp = temperature_1 + ' C'
            TEMP_text_area = label.Label(large_font, text=text_temp, color=text_color)
            TEMP_text_area.x = 24
            TEMP_text_area.y = 75
            group[1] = TEMP_text_area

            text_hum = humidity_1 + ' %'
            HUM_text_area = label.Label(large_font, text=text_hum, color=text_color)
            HUM_text_area.x = 40
            HUM_text_area.y = 125
            group[2] = HUM_text_area

            text_wind = wind_1 + ' km/h'
            WIND_text_area = label.Label(large_font, text=text_wind, color=text_color)
            WIND_text_area.x = 22
            WIND_text_area.y = 220
            group[3] = WIND_text_area

            print('CURRENT weather updated succesfully after # ', current_try_count,' attempt', '\n')
        except Exception as error:
            print('JSON parsing attempt ', current_try_count, '/', attempts, ' failed. Retrying...', error)
            esp.reset()
            connect_to_wifi()
            time.sleep(error_delay)
            if current_try_count >= attempts:
                raise Exception('Current weather update failed ', attempts, ' times')
            continue
    json_weather_data_1_response.close()
    json_weather_data_1_response = None

def update_forecast(): # update FORECAST array and barcharts
    print('-'*40)
    print('Updating FORECASTS...')
    print('-'*40, '\n')

    global forecast_array
    forecast_try_count = 0
    json_forecast_data = None

    while not json_forecast_data:
        try:
            forecast_try_count += 1
            print('FORECASTS update attempt ', forecast_try_count, '/', attempts, '\n')
            forecast_data = requests.get(FORECAST_WEATHER_DATA_SOURCE, timeout=10)
            json_forecast_data = forecast_data.json()
        except Exception as error:
            print('FORECASTS update attempt ', forecast_try_count, '/', attempts, ' failed. Retrying...\n', error)
            esp.reset()
            connect_to_wifi()
            time.sleep(error_delay)
            if forecast_try_count >= attempts:
                raise Exception('FORECASTS update failed ', attempts, ' times')
            continue

    # intermittent errors
        # esp32spi_socket.py didn't receive full response, failing out
        # adafruit_requests.py line 132 in json ValueError: syntax error in JSON
        # File "adafruit_esp32spi/adafruit_esp32spi.py", line 275, in _wait_spi_char RuntimeError: Error response to command
        # File "adafruit_requests.py", line 223, in request ValueError: invalid syntax for integer with base 10
        # File "adafruit_esp32spi/adafruit_esp32spi.py", line 589, in get_host_by_name RuntimeError: Failed to request hostname

    # print(json_forecast_data)
    # forecast_array = ( (forecast, utc, struct_time, icon, temp, rain, sun, wind) )
    forecast_array = []
    for forecast in range(0, Forecast_nb - 1): # number of forecasts
        utc = json_forecast_data['list'][forecast]['dt']
        struct_time = time.localtime(utc)
        # print(struct_time)
        icon = json_forecast_data['list'][forecast]['weather'][0]['icon']
        temp =  json_forecast_data['list'][forecast]['main']['temp']
        try:
            rain = json_forecast_data['list'][forecast]['rain']['3h']
        except KeyError:
            rain = 0
        try:
            cloud = 100 - json_forecast_data['list'][forecast]['clouds']['all']
        except KeyError:
            cloud = 0
            print('sun error forecast ' + str(forecast))
        try:
            wind = json_forecast_data['list'][forecast]['wind']['speed']
        except KeyError:
            wind = 0
            print('wind error forecast ' + str(forecast))
        try:
            humidity = json_forecast_data['list'][forecast]['main']['humidity']
        except KeyError:
            humidity = 0
            print('humidity error forecast ' + str(forecast))
        forecast_array.append((forecast, utc, struct_time, icon, temp, rain, cloud, wind, humidity))
    print('len of forecast array', len(forecast_array), '\n')
    # forecast_array content = ( (0 forecast, 1 utc, 2 struct_time, 3 icon, 4 temp, 5 rain, 6 cloud, 7 wind, 8 humidity) )
    draw_bar_chart(6, sun_min, sun_max, (180, 48), (319, 1), 2)  # SUN/CLOUDS
    draw_bar_chart(4, temp_min, temp_max, (180, 96), (319, 49), 6)  # TEMP
    draw_bar_chart(8, hum_min, hum_max, (180, 144), (319, 97), 4)  # HUMIDITY
    draw_bar_chart(5, rain_min, rain_max, (180, 192), (319, 145), 1)  # RAIN
    draw_bar_chart(7, wind_min, wind_max, (180, 239), (319, 193), 5)  # WIND
    draw_day_line((180,HEIGHT), (WIDTH,0)) # draw day line
    print('Sunrise: ', TZ(time.localtime(SUNRISE).tm_hour), ':', time.localtime(SUNRISE).tm_min, ' | Sunset: ', TZ(time.localtime(SUNSET).tm_hour), ':', time.localtime(SUNSET).tm_min)
    forecast_data.close()
    forecast_data = None
    print('FORECASTS updated succesfully after # ', forecast_try_count, ' attempts', '\n')


#############################################
# WEATHER DATA LOCATION                     #
#############################################
print('-'*40)
print('URLs')
print('-'*40, '\n')

CURRENT_WEATHER_DATA_SOURCE_1 = 'http://api.openweathermap.org/data/2.5/weather?id='+str(WEATHER_LOCATION)
CURRENT_WEATHER_DATA_SOURCE_1 += '&units=metric&appid='+secrets['openweather_token']
print('CURRENT weather API URL: ', CURRENT_WEATHER_DATA_SOURCE_1)

FORECAST_WEATHER_DATA_SOURCE = 'http://api.openweathermap.org/data/2.5/forecast?id=' + str(WEATHER_LOCATION)
FORECAST_WEATHER_DATA_SOURCE += '&units=metric&appid=' + secrets['openweather_token'] + '&cnt=30'  # limiting results
print('FORECASTS weather API URL: ', FORECAST_WEATHER_DATA_SOURCE, '\n')


#############################################
# INFINITE LOOP                             #
#############################################
print('-'*40)
print('Beginning infinite loop...')
print('-'*40, '\n')

last_update_displayed_time, last_update_internet_time, last_update_current_weather, last_update_forecast = 0,0,0,0

while True:

    # UPDATE UPDATE BAR
    progress = int(100*(time.monotonic() - last_update_displayed_time)/displayed_time_update_freq)

    update_updatebar(progress)

    # DISPLAYED TIME
    if time.monotonic() - last_update_displayed_time > displayed_time_update_freq:
        update_displayed_time()
        last_update_displayed_time = time.monotonic()

    # INTERNET TIME
    if time.monotonic() - last_update_internet_time > weather_update_freq:
        update_internet_time()
        last_update_internet_time = time.monotonic()

    # CURRENT WEATHER
    if time.monotonic() - last_update_current_weather > weather_update_freq:
        update_current_weather()
        last_update_current_weather = time.monotonic()

    # FORECASTS
    if time.monotonic() - last_update_forecast > weather_update_freq:
        update_forecast()
        last_update_forecast = time.monotonic()

    # BRIGHTNESS
    board.DISPLAY.brightness = simpleio.map_range(light.value, 0, 40000, 0, 100) / 100

    # CLEAR MEMORY
    print('X Clear memory... Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()),end='')
    gc.collect()
    print(' | Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()),end='')
    print(' | Progress: {:02.0f}'.format(progress), '%', '\n')


    # UPDATE DISPLAY
    display.show(group)

    time.sleep(update_freq)
