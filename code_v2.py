""" Will display on PyPortal current temperature, humidity, wind and time as well as forecast bar chart
requires secrets.py with wifi connection details, openwetaher and adafruitio keys.
"""




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
    print("Secrets key such as WIFI are kept in secrets.py, please add them there!")
    raise


#############################################
# SETTINGS                                  #
#############################################

WEATHER_LOCATION = 2998264 # 1850147 = Tokyo, 3909360 = Okinawa, 2998264 = Limoux
sun_min = 0     # %
sun_max = 100   # %
temp_min = 0   # Celsius
temp_max = 15   # Celsius
hum_min = 30    # %
hum_max = 100   # %
rain_min = 0    # mm
rain_max = 5   # mm
wind_min = 0    # km/h
wind_max = 30   # km/h
TZ_offset = 1   # difference between City and GMT TOKYO = 9
Forecast_nb = 16 # 16 = 2 days

cwd = ("/"+__file__).rsplit('/', 1)[0]  # the current working directory (where this file is)

small_font = bitmap_font.load_font(cwd+"/fonts/mono-bold-8.bdf")
large_font = bitmap_font.load_font(cwd+"/fonts/Arial-Bold-24.bdf")
text_color = 0xffffff

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

#############################################
# CONNECT TO WIFI                           #
#############################################

print("Connecting to WIFI...")
while not esp.is_connected:
    try:
        time.sleep(1)
        esp.connect_AP(secrets['ssid'], secrets['password'])
    except RuntimeError as e:
        print("Could not connect to WIFI, retrying: ", e)
        continue
print("Connected to", str(esp.ssid, 'utf-8'), "\tRSSI:", esp.rssi, "   IP address is", esp.pretty_ip(esp.ip_address), '\n')

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print("\nPYPORTAL found and in idle mode")

requests.set_socket(socket, esp)

# requests.set_interface(esp)

#############################################
# CREATE DISPLAY SETUP                      #
#############################################
print("Creating DISPLAY...")
display = board.DISPLAY
light = analogio.AnalogIn(board.LIGHT)

board.DISPLAY.brightness = 1
HEIGHT = display.height
WIDTH = display.width
group = displayio.Group(max_size=10)

##### BAR CHART LAYER ##### 0
BC_bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(8)
palette[0] = 0x000000  # BLACK
palette[1] = 0x0000ff  # BLUE RAIN
palette[2] = 0xFFFF00  # YELLOW SUN
palette[4] = 0x90A9D4  # LIGHT BLUE HUMIDITY
palette[5] = 0x858585  # GREY WIND
palette[6] = 0xFC538A  # ROUGE TEMP
palette[7] = 0xffffff  # WHITE
BC_tile_grid = displayio.TileGrid(BC_bitmap, pixel_shader=palette)

group.append(BC_tile_grid)

##### TEMPERATURE LAYER ##### 1
text_temp = " "
TEMP_text_area = label.Label(large_font, text=text_temp, color=text_color)
group.append(TEMP_text_area)

##### HUMIDITY LAYER ##### 2
text_hum = " "
HUM_text_area = label.Label(large_font, text=text_hum, color=text_color)
group.append(HUM_text_area)

##### WIND LAYER ##### 3
text_wind = " "
WIND_text_area = label.Label(large_font, text=text_wind, color=text_color)
group.append(WIND_text_area)

##### TIME LAYER ##### 4
text_time = " "
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

print("DISPLAY created succesfully\n")

#############################################
# FUNCTIONS                                 #
#############################################

def TZ(mytime):
    if mytime + TZ_offset > 24:
        mytime = mytime + TZ_offset - 24
    else:
        mytime = mytime + TZ_offset
    return mytime

def draw_day_line(bottom_left, top_right):
    x_max = top_right[0]
    x_min = bottom_left[0]
    bar_width = int((top_right[0] - bottom_left[0]) / Forecast_nb)
    line_width = 1

    for forecast in range(0, Forecast_nb - 1):
        if forecast_array[forecast][2].tm_hour == 21:
            for y in range(0,HEIGHT):
                BC_bitmap[x_min + (1+forecast)*bar_width, y] = 6
        if forecast_array[forecast][2].tm_hour == 9:
            for y in range(0,HEIGHT):
                if (y % 3) == 0:
                    BC_bitmap[x_min + (1+forecast)*bar_width, y] = 5


def draw_bar_chart(UI_index, UI_min, UI_max, bottom_left, top_right, color):
    y_min = top_right[1]
    y_max = bottom_left[1]
    bar_width = int((top_right[0] - bottom_left[0]) / Forecast_nb)

    for forecast in range(0, Forecast_nb - 1):
        UI = forecast_array[forecast][UI_index]

        # add a min level of SUN to identify days and nights
        if UI_index == 6: # add a min level of sun to identify days and nights
            y_bar = min(simpleio.map_range(UI, UI_min, UI_max, y_max, y_min), y_max - 2)
            print(TZ(forecast_array[forecast][2].tm_hour), TZ(time.localtime(SUNRISE).tm_hour), TZ(time.localtime(SUNSET).tm_hour),UI_index == 6 and not((TZ(forecast_array[forecast][2].tm_hour) > TZ(time.localtime(SUNRISE).tm_hour)) and (TZ(forecast_array[forecast][2].tm_hour) < TZ(time.localtime(SUNSET).tm_hour))))
        else:
            y_bar = simpleio.map_range(UI, UI_min, UI_max, y_max, y_min)

        # If UI_index is SUN, and if forecast time is after SUNRISE and before SUNSET, set color to yelow
        if (UI_index == 6) and not((TZ(forecast_array[forecast][2].tm_hour) > TZ(time.localtime(SUNRISE).tm_hour)) and (TZ(forecast_array[forecast][2].tm_hour) < TZ(time.localtime(SUNSET).tm_hour))):
            color_bis = 5
        else:
            color_bis = color

        if UI_index == 4: # temp
            print("FORECAST HOUR: ", TZ(forecast_array[forecast][2].tm_hour), "SUNSET:", TZ(time.localtime(SUNSET).tm_hour), "SUNRISE:", TZ(time.localtime(SUNRISE).tm_hour), "TEMP: ", UI, "C")

        for x in range(max(0, int(bottom_left[0]+forecast*bar_width + 1)), min(WIDTH-1, bottom_left[0]+(1+forecast)*bar_width)):

            for y in range(max(y_min, int(y_bar), 0), min(HEIGHT-1, y_max)):
                BC_bitmap[x, y] = color_bis

def get_local_time():
    TIME_SERVICE = "https://io.adafruit.com/api/v2/%s/integrations/time/strftime?x-aio-key=%s"
    TIME_SERVICE_STRFTIME = '&fmt=%25Y-%25m-%25d+%25H%3A%25M%3A%25S.%25L+%25j+%25u+%25z+%25Z'

    api_url = None
    try:
        aio_username = secrets['aio_username']
        aio_key = secrets['aio_key']
        location = secrets['timezone']
    except KeyError:
        raise KeyError("\n\nOur time service requires a login/password to rate-limit. Please register for a free adafruit.io account and place the user/key in your secrets file under 'aio_username' and 'aio_key'")

    if location:
        print("Updating time based on timezone ", location)
        api_url = (TIME_SERVICE + "&tz=%s") % (aio_username, aio_key, location)
    else:
        print("Updating time based on IP address")
        api_url = TIME_SERVICE % (aio_username, aio_key)
    api_url += TIME_SERVICE_STRFTIME
    print("Time API URL: \n", api_url)

    try:
        response = requests.get(api_url)

        if esp._debug:
            print("Time request: ", api_url)
            print("Time reply: ", response.text)
        print("Time reply: ", response.text)
        times = response.text.split(' ')
        the_date = times[0]
        the_time = times[1]
        year_day = int(times[2])
        week_day = int(times[3])
        is_dst = None
    except KeyError:
        raise KeyError("Was unable to update the time, try setting secrets['timezone'] according to http://worldtimeapi.org/timezones")

    year, month, mday = [int(x) for x in the_date.split('-')]
    the_time = the_time.split('.')[0]
    hours, minutes, seconds = [int(x) for x in the_time.split(':')]
    now_struct = time.struct_time((year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst))
    rtc.RTC().datetime = now_struct
    response.close()
    response = None

#############################################
# CURRENT WEATHER DATA LOCATION             #
#############################################
CURRENT_WEATHER_DATA_SOURCE_1 = "http://api.openweathermap.org/data/2.5/weather?id="+str(WEATHER_LOCATION)
CURRENT_WEATHER_DATA_SOURCE_1 += "&units=metric&appid="+secrets['openweather_token']
print("CURRENT weather API URL: \n", CURRENT_WEATHER_DATA_SOURCE_1)

#############################################
# WEATHER FORECAST DATA LOCATION            #
#############################################
FORECAST_WEATHER_DATA_SOURCE = "http://api.openweathermap.org/data/2.5/forecast?id=" + str(WEATHER_LOCATION)
FORECAST_WEATHER_DATA_SOURCE += "&units=metric&appid=" + secrets['openweather_token'] + "&cnt=30"  # limiting results
print("FORECASTS weather API URL: \n", FORECAST_WEATHER_DATA_SOURCE, '\n')

localtime_refresh = None
localtime_last_failed_try = 0
current_weather_refresh = None
forecast_weather_refresh = None

#############################################
# INFINITE LOOP                             #
#############################################
print("Beginning infinite loop...\n")

while True:

    # UPDATE LOCAL TIME ##################################################################################
    if (not localtime_refresh) or ((time.monotonic() - localtime_refresh) > 300 and (time.monotonic() - localtime_last_failed_try) > 30):
        try:
            print("Updating LOCAL TIME from internet...")
            get_local_time()
            localtime_refresh = time.monotonic()
            print("LOCAL TIME updated succesfully\n")
        except:  # RuntimeError as e:
            localtime_last_failed_try = time.monotonic()
            print("Some error occured updating LOCAL TIME")
            continue

    # UPDATE CURRENT WEATHER ###################################################################### LAYER 1
    if (not current_weather_refresh) or (time.monotonic() - current_weather_refresh) > 300:
        try:
            print("Updating CURRENT weather...")
            json_weather_data_1 = requests.get(CURRENT_WEATHER_DATA_SOURCE_1).json()  # JSON 1

            weather_1 = json_weather_data_1['weather'][0]['description']
            temperature_1 = "{:.1f}".format(json_weather_data_1['main']['temp'])
            humidity_1 = "{:.0f}".format(json_weather_data_1['main']['humidity'])
            wind_1 = "{:.0f}".format(json_weather_data_1['wind']['speed'])
            SUNRISE = json_weather_data_1['sys']['sunrise']
            SUNSET = json_weather_data_1['sys']['sunset']

            text_temp = temperature_1 + " C"
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

            current_weather_refresh = time.monotonic()
            print("CURRENT weather updated succesfully\n")
        except:  # RuntimeError as e:
            print("Some error occured retrieving CURRENT weather, retrying!")
            continue

    # UPDATE FORECAST ##################################################################################
    if (not forecast_weather_refresh) or (time.monotonic() - forecast_weather_refresh) > 30:
        try:
            print("Updating FORECASTS...")
            json_forecast_data = requests.get(FORECAST_WEATHER_DATA_SOURCE).json()
            # print(json_forecast_data)
            # forecast_array = ( (forecast, utc, struct_time, icon, temp, rain, sun, wind) )
            forecast_array = []
            for forecast in range(0, Forecast_nb - 1): # number of forecasts
                utc = json_forecast_data['list'][forecast]['dt']
                struct_time = time.localtime(utc)
                print(struct_time)
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
#                 if (time.time()-utc)<10800:
                forecast_array.append((forecast, utc, struct_time, icon, temp, rain, cloud, wind, humidity))
            print("len of forecast array", len(forecast_array))
            # forecast_array = ( (0 forecast, 1 utc, 2 struct_time, 3 icon, 4 temp, 5 rain, 6 cloud, 7 wind, 8 humidity) )
            draw_bar_chart(6, sun_min, sun_max, (180, 48), (319, 0), 2)  # SUN/CLOUDS
            draw_bar_chart(4, temp_min, temp_max, (180, 96), (319, 49), 6)  # TEMP
            draw_bar_chart(8, hum_min, hum_max, (180, 144), (319, 97), 4)  # HUMIDITY
            draw_bar_chart(5, rain_min, rain_max, (180, 192), (319, 145), 1)  # RAIN
            draw_bar_chart(7, wind_min, wind_max, (180, 239), (319, 193), 5)  # WIND
            draw_day_line((180,HEIGHT), (WIDTH,0)) # draw day line
            print("Sunrise: ", TZ(time.localtime(SUNRISE).tm_hour), ":", time.localtime(SUNRISE).tm_min)
            print("Sunset: ", TZ(time.localtime(SUNSET).tm_hour), ":", time.localtime(SUNSET).tm_min)
            for forecast in range(0, Forecast_nb - 1):
                print(forecast,":",
                    forecast_array[forecast][2].tm_mday,"/",
                    forecast_array[forecast][2].tm_mon,"/",
                    forecast_array[forecast][2].tm_year," - ",
                    TZ(forecast_array[forecast][2].tm_hour),":",
                    forecast_array[forecast][2].tm_min,":",
                    forecast_array[forecast][2].tm_sec,
                    "-ICON:",forecast_array[forecast][3],
                    "-TEMP:",forecast_array[forecast][4],
                    "-RAIN:",forecast_array[forecast][5],
                    "-SUN:",forecast_array[forecast][6],
                    "-WIND:",forecast_array[forecast][7],
                    "-HUMIDITY:",forecast_array[forecast][8])
            forecast_weather_refresh = time.monotonic()
            print("FORECASTS Bar Chart updated succesfully\n")
        except RuntimeError as e:
            print("Some error occured retrieving FORECASTS, retrying! error type:", e)
            time.sleep(10)
            continue

    # UPDATE TIME ######################################################################
    try:
        print("Updating DISPLAYED TIME...")
        mytime = time.localtime(time.time())
        (year, month, day, hour, minute, second, wday, yday, isdst) = mytime
        text_time = '{:02.0f}'.format(hour)+":"+'{:02.0f}'.format(minute) # +":"+'{:02.0f}'.format(second)
#         print('{:02.0f}'.format(hour)+":"+'{:02.0f}'.format(minute) +":"+'{:02.0f}'.format(second))
        TIME_text_area = label.Label(large_font, text=text_time, color=text_color)
        TIME_text_area.x = 28
        TIME_text_area.y = 30
        group[4] = TIME_text_area
        print("DISPLAYED TIME updated succesfully at: ", '{:02.0f}'.format(hour)+":"+'{:02.0f}'.format(minute) +":"+'{:02.0f}'.format(second), '\n')
    except: # RuntimeError as e:
        print("Some error occured updating DISPLAYED TIME, retrying!")
        continue

    lightvalue = simpleio.map_range(light.value, 0, 40000, 0, 100)
    board.DISPLAY.brightness = lightvalue / 100

    print('Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()))
    gc.collect()
    print('Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()),'\n')

    display.show(group)

    time.sleep(60)
