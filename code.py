  """ will display current temperature, humidity, wind and time. as well as forecast bar chart
requires secrets.py with wifi connection details, openwetaher and adafruitio keys
"""
import board
import os
import storage
import adafruit_sdcard
import displayio
import simpleio
import digitalio
import analogio
import busio
import time
import json
import rtc
import gc
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_esp32spi.adafruit_esp32spi_requests as requests
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

CURRENT_WEATHER_LOCATION_1 = 5128581 # New York code


cwd = ("/"+__file__).rsplit('/', 1)[0] # the current working directory (where this file is)

small_font = cwd+"/fonts/Arial-12.bdf"
medium_font = cwd+"/fonts/Arial-16.bdf"
large_font = cwd+"/fonts/Arial-Bold-24.bdf"

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset, debug=False)

cs = digitalio.DigitalInOut(board.SD_CS)
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)
storage.mount(vfs, "/sd")
os.listdir('/sd')


requests.set_interface(esp)

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print("\nESP32 found and in idle mode")

#############################################
# CONNECT TO WIFI                           #
#############################################

print("Connecting to WIFI...")
while not esp.is_connected:
    try:
        time.sleep(1)
        esp.connect_AP(secrets['ssid'], secrets['password'])
    except RuntimeError as e:
        print("Could not connect to WIFI, retrying: ",e)
        continue
print("Connected to", str(esp.ssid, 'utf-8'), "\tRSSI:", esp.rssi)
print("IP address is", esp.pretty_ip(esp.ip_address), '\n')


#############################################
# CREATE DISPLAY SETUP                      #
#############################################

display = board.DISPLAY
light = analogio.AnalogIn(board.LIGHT)

board.DISPLAY.brightness = 1
HEIGHT = display.height
WIDTH = display.width
group = displayio.Group(max_size=10)

##### BAR CHART LAYER ##### 0
BC_bitmap = displayio.Bitmap(WIDTH, HEIGHT, 8)
palette = displayio.Palette(8)
palette[0] = 0x000000 # BLACK
palette[1] = 0x0000ff # BLUE RAIN
palette[2] = 0xFFFF00 # YELLOW SUN
palette[4] = 0x90A9D4 # LIGHT BLUE HUMIDITY
palette[5] = 0x858585 # GREY WIND
palette[6] = 0xFC538A # ROUGE TEMP
palette[7] = 0xffffff # WHITE
BC_tile_grid = displayio.TileGrid(BC_bitmap, pixel_shader=palette)

group.append(BC_tile_grid)

##### TEMPERATURE LAYER ##### 1
text_temp = " "
font = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
color = 0xffffff
TEMP_text_area = label.Label(font, text=text_temp, color=color)
group.append(TEMP_text_area)

##### HUMIDITY LAYER ##### 2
text_hum = " "
font = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
color = 0xffffff
HUM_text_area = label.Label(font, text=text_hum, color=color)
group.append(HUM_text_area)

##### WIND LAYER ##### 3
text_wind = " "
font = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
color = 0xffffff
WIND_text_area = label.Label(font, text=text_wind, color=color)
group.append(WIND_text_area)

##### TIME LAYER ##### 4
text_time = " "
font = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
color = 0xffffff
TIME_text_area = label.Label(font, text=text_time, color=color)
group.append(TIME_text_area)

#############################################
# FUNCTIONS                                 #
#############################################

def draw_bar_chart(UI_index, UI_min, UI_max, bottom_left, top_right, color):
    y_min = top_right[1]
    y_max = bottom_left[1]
    bar_width =  int((top_right[0] - bottom_left[0])/ forecast_num)
    bar_height = int(y_max - y_min)
    for forecast in range(len(forecast_array)):
        UI = forecast_array[forecast][UI_index]
        y_bar = simpleio.map_range(100*UI/(UI_max-UI_min), 0, 100, y_max, y_min)
        if UI_index == 6 and (forecast_array[forecast][2].tm_hour > (time.localtime(SUNSET).tm_hour + 9)  or forecast_array[forecast][2].tm_hour < (time.localtime(SUNRISE).tm_hour - 15)):
            color_bis = 5
            print("FORECAST HOUR: ",forecast_array[forecast][2].tm_hour, "SUNSET:",time.localtime(SUNSET).tm_hour + 9,"SUNRISE:", time.localtime(SUNRISE).tm_hour - 15)
        else:
            color_bis = color
        for x in range(max(0, int(bottom_left[0]+forecast*bar_width + 1)), min(WIDTH-1, bottom_left[0]+(1+forecast)*bar_width)):
            for y in range(max(y_min, int(y_bar), 0), min(HEIGHT-1, y_max)):
                BC_bitmap[x,y] = color_bis

def get_local_time():
    IMAGE_CONVERTER_SERVICE = "https://io.adafruit.com/api/v2/%s/integrations/image-formatter?x-aio-key=%s&width=%d&height=%d&output=BMP%d&url=%s"
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
        print("Getting time for timezone", location)
        api_url = (TIME_SERVICE + "&tz=%s") % (aio_username, aio_key, location)
    else:
        print("Getting time from IP address")
        api_url = TIME_SERVICE % (aio_username, aio_key)
    api_url += TIME_SERVICE_STRFTIME
    print(api_url)

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
        raise KeyError("Was unable to lookup the time, try setting secrets['timezone'] according to http://worldtimeapi.org/timezones")

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
CURRENT_WEATHER_DATA_SOURCE_1 = "http://api.openweathermap.org/data/2.5/weather?id="+str(CURRENT_WEATHER_LOCATION_1)
CURRENT_WEATHER_DATA_SOURCE_1 += "&units=metric&appid="+secrets['openweather_token']
print(CURRENT_WEATHER_DATA_SOURCE_1)

#############################################
# WEATHER FORECAST DATA LOCATION            #
#############################################
FORECAST_WEATHER_LOCATION = 1850147 # Tokyo
FORECAST_WEATHER_DATA_SOURCE = "http://api.openweathermap.org/data/2.5/forecast?id="+str(FORECAST_WEATHER_LOCATION)
FORECAST_WEATHER_DATA_SOURCE += "&units=metric&appid="+secrets['openweather_token']+"&cnt=20" # limiting results 
print(FORECAST_WEATHER_DATA_SOURCE, '\n')

localtime_refresh = None
localtime_last_failed_try = 0
current_weather_refresh = None
forecast_weather_refresh = None

#############################################
# INFINITE LOOP                             #
#############################################
while True:

    # UPDATE LOCAL TIME ##################################################################################
    if (not localtime_refresh) or ((time.monotonic() - localtime_refresh) > 60 and (time.monotonic() - localtime_last_failed_try) > 30) :
        try:
            print("Getting time from internet!")
            get_local_time()
            localtime_refresh = time.monotonic()
            print('Local time updated\n')
        except RuntimeError as e:
            localtime_last_failed_try = time.monotonic()
            print("Some error occured, retrying in 5'! -", e)
            continue

    # UPDATE CURRENT WEATHER ###################################################################### LAYER 1
    if (not current_weather_refresh) or (time.monotonic() - current_weather_refresh) > 30:
        try:
            json_weather_data_1 = requests.get(CURRENT_WEATHER_DATA_SOURCE_1).json() # JSON 1
            weather_1 = json_weather_data_1['weather'][0]['description']
            temperature_1 = "{:.1f}".format(json_weather_data_1['main']['temp'])
            humidity_1 = "{:.0f}".format(json_weather_data_1['main']['humidity'])
            wind_1 = "{:.0f}".format(json_weather_data_1['wind']['speed'])
            SUNRISE = json_weather_data_1['sys']['sunrise']
            SUNSET = json_weather_data_1['sys']['sunset']
            
            text_temp = temperature_1 + " C"
            TEMP_text_area = label.Label(font, text=text_temp, color=color)
            TEMP_text_area.x = 40
            TEMP_text_area.y = 80
            group[1] = TEMP_text_area
            
            text_hum = humidity_1 + ' %'
            HUM_text_area = label.Label(font, text=text_hum, color=color)
            HUM_text_area.x = 50
            HUM_text_area.y = 130
            group[2] = HUM_text_area
            
            text_wind = wind_1 + ' km/h'
            WIND_text_area = label.Label(font, text=text_wind, color=color)
            WIND_text_area.x = 35
            WIND_text_area.y = 180
            group[3] = WIND_text_area
            
            current_weather_refresh = time.monotonic()
            print("Current weather updated, temperature: ", text_temp, sep=' ', end='\n')
        except RuntimeError as e:
            print("Some error occured retrievent current weather, retrying! - ", e)
            continue

    # UPDATE FORECAST ##################################################################################
    if (not forecast_weather_refresh) or (time.monotonic() - forecast_weather_refresh) > 60: 
        try:
            json_forecast_data = requests.get(FORECAST_WEATHER_DATA_SOURCE).json()
            
            # forecast_array = ( (forecast, utc, struct_time, icon, temp, rain, sun, wind) )
            forecast_array = []
            for forecast in range(17): # number of forecasts
                utc = json_forecast_data['list'][forecast]['dt']
                struct_time = time.localtime(utc)
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
                if (time.time()-utc)<10800:
                    forecast_array.append((forecast, utc, struct_time, icon, temp, rain, cloud, wind, humidity))
            forecast_num = len(forecast_array)
            # forecast_array = ( (0 forecast, 1 utc, 2 struct_time, 3 icon, 4 temp, 5 rain, 6 cloud, 7 wind, 8 humidity) )
            draw_bar_chart(4, 0, 30, (180,48), (319,0), 6) # TEMP
            draw_bar_chart(6, 0, 100, (180,96), (319,49), 2) # SUN/CLOUDS
            draw_bar_chart(8, 0, 100, (180,144), (319,97), 4) # HUMIDITY
            draw_bar_chart(5, 0, 5, (180,192), (319,145), 1) # RAIN
            draw_bar_chart(7, 0, 30, (180,239), (319,193), 5) # WIND
            print("sunrise: ", time.localtime(SUNRISE).tm_hour - 15)
            print("sunset: ", time.localtime(SUNSET).tm_hour + 9)
            for forecast in range(len(forecast_array)):
                print(forecast,":",
                    forecast_array[forecast][2].tm_mday,"/",
                    forecast_array[forecast][2].tm_mon,"/",
                    forecast_array[forecast][2].tm_year," - ",
                    forecast_array[forecast][2].tm_hour,":",
                    forecast_array[forecast][2].tm_min,":",
                    forecast_array[forecast][2].tm_sec,
                    "-ICON:",forecast_array[forecast][3],
                    "-TEMP:",forecast_array[forecast][4],
                    "-RAIN:",forecast_array[forecast][5],
                    "-SUN:",forecast_array[forecast][6],
                    "-WIND:",forecast_array[forecast][7],
                    "-HUMIDITY:",forecast_array[forecast][8])
            forecast_weather_refresh = time.monotonic()
            print("Forecast Bar Chart updated", sep=' ', end='\n')
        except RuntimeError as e:
            print("Some error occured retrieving forecast, retrying! - ", e)
            continue

    # UPDATE TIME ######################################################################
    try:
        mytime = time.localtime(time.time())
        (year, month, day, hour, minute, second, wday, yday, isdst) = mytime
        text_time = '{:02.0f}'.format(hour)+":"+'{:02.0f}'.format(minute) # +":"+'{:02.0f}'.format(second)
        print('{:02.0f}'.format(hour)+":"+'{:02.0f}'.format(minute) +":"+'{:02.0f}'.format(second))
        TIME_text_area = label.Label(font, text=text_time, color=color)
        TIME_text_area.x = 45
        TIME_text_area.y = 20
        group[4] = TIME_text_area
    except RuntimeError as e:
        print("Some error occured updating time, retrying! - ", e)
        continue

    lightvalue = simpleio.map_range(light.value, 0, 64000, 0, 100)
    board.DISPLAY.brightness = lightvalue / 100
    print('Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()))
    gc.collect()
    print('Mem free: {:,} allocated: {:,}'.format(gc.mem_free(), gc.mem_alloc()))

    display.refresh_soon()
    display.show(group)
    time.sleep(10)
