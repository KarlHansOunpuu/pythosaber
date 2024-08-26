'''
Pythosaber Version 1.0.0 "The Initiate"
An RP2040-based lightsaber soundboard project
written in CircuitPython

by Karl Hans Õunpuu, Tallinn, Estonia
25th July 2024

MIT License

'''
# == Declare Imports == #
import board
import time, gc
import busio, digitalio

import os, sdcardio, storage, json
import audiobusio, audiocore, audiomixer
import neopixel

import math
from ulab import numpy as np

from adafruit_lsm6ds import Rate, AccelRange, GyroRange
from adafruit_lsm6ds.lsm6dsox import LSM6DSOX


# == Boot System == #
current_state = "BOOTING"

gc.enable()

# Initialize timekeeping
time_current = time.monotonic()
time_previous = time_current

print('=== Pythosaber Version 1.0.0 "The Initiate" ===')
print('=== BOOTING ===')

# == Initialize Hardware == #
# Board Interface
board_led = neopixel.NeoPixel(
    board.NEOPIXEL,
    1,
    pixel_order=neopixel.GRB,
    auto_write=False
    )

board_button = digitalio.DigitalInOut(board.BUTTON)
board_button.switch_to_input(pull=digitalio.Pull.UP)

# SD Card
print('SD Card mounting...')
try:
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    cs = board.A0
    sdcard = sdcardio.SDCard(spi, cs)
    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, '/sd')
except Exception as e:
    print('SD Card mounting failed')
    print('Exception {} {}\n'.format(type(e).__name__, e))
finally:
    print('SD Card mounted as: /sd.')
    print(os.listdir('/sd'))

# Filesystem
config_file = "/sd/config.json"
with open(config_file, "r") as f:
    config = json.loads(f.read())
    current_selection = config["save_state"]

# Sound
print('Initalizing Sound...')
try:
    i2s = audiobusio.I2SOut(board.D3, board.D2, board.D1)

    main_mixer = audiomixer.Mixer(
        voice_count=3,
        buffer_size=2048,
        sample_rate=22050,
        channel_count=1,
        bits_per_sample=16,
        samples_signed=True
    )

    swing_mixer = audiomixer.Mixer(
        voice_count=2,
        buffer_size=2048,
        sample_rate=22050,
        channel_count=1,
        bits_per_sample=16,
        samples_signed=True
    )
except Exception as e:
    print('Sound initialization failed')
    print('Exception {} {}\n'.format(type(e).__name__, e))
finally:
    print('Sound initalized')

# Motion
print('Initializing Motion...')
try:
    i2c = busio.I2C(board.SCL1, board.SDA1)
    motion = LSM6DSOX(i2c)
    motion.accelerometer_range = AccelRange.RANGE_2G
    motion.accelerometer_data_rate = Rate.RATE_26_HZ
    motion.gyro_range = GyroRange.RANGE_2000_DPS
    motion.gyro_data_rate = Rate.RATE_26_HZ
except Exception as e:
    print('Motion initialization failed')
    print('Exception {} {}\n'.format(type(e).__name, e))
finally:
    print('Motion initialized')

# Neopixels
print('Initializing Neopixel blade...')
try:
    blade_pixels = 54
    blade_led = neopixel.NeoPixel(
    board.RX,
    blade_pixels,
    pixel_order=neopixel.GRB,
    auto_write=False
    )
except Exception as e:
    print('Neopixel blade initialization failed')
    print('Exception {} {}\n'.format(type(e).__name, e))
finally:
    print('Neopixel blade initialized')

# Interface
print('Initializing Interface...')
'''
Buttons are connected to GND
This means that the digital signal they output
when not pressed is 1 and when pressed is 0
Not Pressed = True
Pressed = False
'''
try:
    button_main = digitalio.DigitalInOut(board.SDA)
    button_main.switch_to_input(pull=digitalio.Pull.UP)

    button_aux = digitalio.DigitalInOut(board.SCL)
    button_aux.switch_to_input(pull=digitalio.Pull.UP)
except Exception as e:
    print('Interface initialization failed')
    print('Exception {} {}\n'.format(type(e).__name, e))
finally:
    print('Interface initialized')


# == Define Functions == #
# Set initial profile variables
active_profile = "boot"
current_selection = 0
color = (0, 0, 0)
font_path = "/sd/sounds/"
swing_threshold = 0
clash_threshold = 0
lowpass_alpha = 0
swing_sharpness = 0
transition_region_1 = 0
transition_region_2 = 0
transition_point_1 = 0
transition_point_2 = 0

# Profile functions
def print_profile():
    '''
    Prints currently active profile.
    '''
    print(f'''Profile: {active_profile}
          Font Path: {font_path}
          Blade Color: R:{color[0]}, G:{color[1]}, B:{color[2]}
          Swing Threshold: {swing_threshold}
          Clash Threshold: {clash_threshold}
          Filter Alpha: {lowpass_alpha}
          Swing Sharpness: {swing_sharpness}
          Transition Region 1:{transition_region_1} radians
          Transition Region 2:{transition_region_2} radians
          Transition Point 1:{transition_point_1} radians
          Transition Point 2:{transition_point_2} radians
          ''')

def list_profiles():
    '''
    Prints a list of all available profiles in the config.json file.
    For debugging.
    '''
    with open(config_file, "r") as f:
        config = json.loads(f.read())
        profile_names = list(config["profiles"].keys())
        print(f'Available Profiles: {profile_names}')

def load_profile(profile=None):
    '''
    Profile loader.
    Selects specific profile if it's supplied as an argument.
    Cycles through list of profiles from the config file if specific name is not supplied.
    Wraps around when list ends.
    Saves current selection to the config file, so that on board reset, the selection persists.
    '''
    global active_profile
    global current_selection
    global color
    global font_path
    global swing_threshold
    global clash_threshold
    global lowpass_alpha
    global swing_sharpness
    global transition_region_1
    global transition_region_2
    global transition_point_1
    global transition_point_2

    # Unload current sound
    i2s.stop()

    # Open config file
    with open(config_file, "r") as f:
        config = json.loads(f.read())
        profile_names = list(config["profiles"].keys())

    # If specific profile name is given
    if profile:
        try:
            current_selection = profile
            active_profile = profile_names[current_selection]
            color_rgb = config["profiles"][active_profile]["color"]
            if len(color_rgb) != 3:
                print('Invalid RGB values. Using default color.')
                color = (255, 255, 255)
            else:
                pass
        except IndexError:
            print('Invalid index. Jumping to top.')
            current_selection = 0
            active_profile = profile_names[current_selection]
        finally:
            color_rgb = config["profiles"][active_profile]["color"]
            color = tuple(color_rgb)
            font_path = f"/sd/sounds/{active_profile}"
            swing_threshold = float(config["profiles"][active_profile]["swing_threshold"])
            clash_threshold = float(config["profiles"][active_profile]["clash_threshold"])
            lowpass_alpha = float(config["profiles"][active_profile]["filter_alpha"])
            swing_sharpness = float(config["profiles"][active_profile]["swing_sharpness"])
            transition_region_1 = float(config["profiles"][active_profile]["transition_region_1"])
            transition_region_2 = float(config["profiles"][active_profile]["transition_region_2"])
            transition_point_1 = float(config["profiles"][active_profile]["transition_point_1"])
            transition_point_2 = float(config["profiles"][active_profile]["transition_point_2"])
            
            # Save the new selection to config
            config["save_state"] = current_selection
            separators = (", ", ":  ")
            with open(config_file, "w") as f:
                json.dump(config, f, separators=separators)

    # If argument not given - iterate through profiles
    else:
        try:
            current_selection += 1
            active_profile = profile_names[current_selection]
            color_rgb = config["profiles"][active_profile]["color"]
            if len(color_rgb) != 3:
                print('Invalid RGB values. Using default color.')
                color = (255, 255, 255)
            else:
                pass
        except IndexError:
            # If end of profile keys, loop back around
            print('End of profile list. Jumping to top.')
            current_selection = 0  # Reset to first profile
            active_profile = profile_names[current_selection]
        finally:
            color_rgb = config["profiles"][active_profile]["color"]
            color = tuple(color_rgb)
            font_path = f"/sd/sounds/{active_profile}"
            swing_threshold = float(config["profiles"][active_profile]["swing_threshold"])
            clash_threshold = float(config["profiles"][active_profile]["clash_threshold"])
            lowpass_alpha = float(config["profiles"][active_profile]["filter_alpha"])
            swing_sharpness = float(config["profiles"][active_profile]["swing_sharpness"])
            transition_region_1 = float(config["profiles"][active_profile]["transition_region_1"])
            transition_region_2 = float(config["profiles"][active_profile]["transition_region_2"])
            transition_point_1 = float(config["profiles"][active_profile]["transition_point_1"])
            transition_point_2 = float(config["profiles"][active_profile]["transition_point_2"])

            # Save the new selection to config
            config["save_state"] = current_selection
            separators = (", ", ":  ")
            with open(config_file, "w") as f:
                json.dump(config, f, separators=separators)

# Set initial soundfont variables
font = "font.wav"
hum = "hum.wav"
swingh = "swingh/swingh1.wav"
swingl = "swingl/swingl1.wav"
clash = "clsh/clsh1.wav"
ignite = "out/out1.wav"
extinguish = "in/in1.wav"

swingh_list = []
swingl_list = []

hum_volume = 0.0
swing_volume = 0.0
swingh_volume = 0.0
swingl_volume = 0.0

max_hum_volume = 0.9

# Sound functions
def load_soundfont():
    '''
    Loads the currently selected profiles' soundfont.
    '''
    global font, hum, swingh, swingl, clash, pre_on, ignite, extinguish
    global swingh_list, swingl_list
    global main_mixer, swing_mixer
    
    # Close previous sounds
    try:
        font.deinit()
        hum.deinit()
        clash.deinit()
        ignite.deinit()
        extinguish.deinit()
        swingh.deinit()
        swingl.deinit()
        
        # Deinitialize mixer objects to free up resources.
        # This is a hacky way of preventing buffer errors,
        # that lead to crashing.
        swing_mixer.deinit()
        main_mixer.deinit()
        
        gc.collect()
        
        time.sleep(0.42)
        
        # Reinitialize mixer objects
        main_mixer = audiomixer.Mixer(
        voice_count=3,
        buffer_size=2048,
        sample_rate=22050,
        channel_count=1,
        bits_per_sample=16,
        samples_signed=True
        )

        swing_mixer = audiomixer.Mixer(
        voice_count=2,
        buffer_size=2048,
        sample_rate=22050,
        channel_count=1,
        bits_per_sample=16,
        samples_signed=True
        )
        
    except AttributeError:
        print('No font loaded yet. Passing')
        pass
    
    time.sleep(0.42)
    
    # Load main sounds
    font = audiocore.WaveFile(open(font_path + "/font.wav", "rb"))
    hum = audiocore.WaveFile(open(font_path + "/hum.wav", "rb"))
    clash = audiocore.WaveFile(open(font_path + "/clsh/clsh1.wav", "rb"))
    ignite = audiocore.WaveFile(open(font_path + "/out/out1.wav", "rb"))
    extinguish = audiocore.WaveFile(open(font_path + "/in/in1.wav", "rb"))
    
    swingh = audiocore.WaveFile(open(font_path + "/swingh/swingh1.wav", "rb"))
    swingl = audiocore.WaveFile(open(font_path + "/swingl/swingl1.wav", "rb"))
    
    # Play soundfont sound to indicate loading complete
    i2s.play(font, loop=False)

# Smoothswing v2 functions
def calculate_gyro_rms():
    '''
    Takes the raw gyroscope readings (omitting the x-axis, which is "down the barrel"),
    then calculates an estimate of the root mean square i.e the total magnitude
    of the angular velocity of all axes.
    It's not a true RMS calculation, but a good enough approximation,
    and with numpy it's super fast, as opposed to calculating true RMS with roots and squares.
    '''
    gyro_raw = (motion.gyro[1], motion.gyro[2])
    gyro_array = np.array(gyro_raw)
    gyro_rms = np.std(gyro_array)
    return gyro_rms

# Initialize previous gyroscop reading for the filter to use
previous_gyro_filtered = None

def lowpass_filter(data, previous_data, alpha):
    '''
    Simple lowpass filter to smooth out data from sensor readings.
    The alpha value controls the smoothing factor. It should be a number between 0 and 1.
    Lower values smooth more, a value of 1 effectively turns the filter off.
    '''
    if previous_data is None:
        previous_data = data
    filtered_data = alpha * data + (1 - alpha) * previous_data
    return filtered_data

# Initialize accumulated swing & swing strength variables
accumulated_swing = 0
swing_strength = 0

def accumulate_swing_angle(gyro_filtered, time_delta, accumulated_swing):
    '''
    When the gyroscope reading crosses the set threshold, this function is called.
    It starts tracking the accumulated swing angle each time delta tick,
    and wraps around at 360 degrees (2*PI).
    '''
    accumulated_delta = gyro_filtered * time_delta
    accumulated_swing += accumulated_delta
    accumulated_swing %= (2 * math.pi)
    return accumulated_swing

def calculate_swing_strength(gyro_filtered, swing_sharpness):
    '''
    Calculates the swing_strength variable, which is used
    to modulate the volumes of the main sound mixer object.
    '''
    swing_strength = min(1, gyro_filtered / (math.pi))
    swing_strength = swing_strength ** swing_sharpness
    return swing_strength

def do_crossfade(transition_region, transition_point):
    '''
    Performs a linear crossfade between two sounds,
    based on the set transition region, which sets the duration of the crossfade,
    and the accumulated swing, which controls where we are in the crossfade.
    It also accounts for the set transition point, i.e where within the accumulated swing the crossfade starts.
    '''
    progress = max(0.0, min(1.0, (accumulated_swing - transition_point) / transition_region))
    fade_out = max(0.0, (max_hum_volume - progress))
    fade_in = min(max_hum_volume, progress)
    return fade_out, fade_in


# Interface functions
def poll_button_main():
    if not button_main.value:
        cycle_power()
        time.sleep(0.1)
    else:
        pass

def poll_button_aux():
    if not button_aux.value:
            load_profile()
            load_soundfont()
            print_profile()
            gc.collect()
            time.sleep(0.1)
    else:
        pass


# Lightsaber functions
def print_state():
    print(f"State: {current_state}")

def cycle_power():
    global current_state
    global hum_volume

    # If not ignited then ignite
    if current_state == "STANDBY":
        current_state = "CYCLING"
        print_state()

        # Play ignition sound & mixers and set initial levels
        i2s.play(main_mixer)
        main_mixer.voice[0].play(hum, loop=True)
        main_mixer.voice[0].level = hum_volume
        main_mixer.voice[2].play(ignite, loop=False)
        main_mixer.voice[2].level = 1.0

        # Animate the blade in and fade hum sound in
        for p in range(0, blade_pixels, 2):
            if p + 1 < blade_pixels:
                blade_led[p] = color
                blade_led[p + 1] = color
            else:
                blade_led[p] = color
            blade_led.show()
            hum_volume = min(max_hum_volume, (hum_volume + 0.042))
            main_mixer.voice[0].level = hum_volume
            time.sleep(0.01)

        # Play the swing mixer in the background
        main_mixer.voice[1].play(swing_mixer, loop=True)
        main_mixer.voice[1].level = swing_volume
        swing_mixer.voice[0].play(swingh, loop=True)
        swing_mixer.voice[0].level = 0.0
        swing_mixer.voice[1].play(swingl, loop=True)
        swing_mixer.voice[1].level = 0.0

        # For safety fill the whole blade with current color
        blade_led.fill(color)
        blade_led.show()

        # Set the global state
        current_state = "ACTIVE"
        print_state()

    # If ignited then extinguish
    elif current_state == "ACTIVE":
        current_state = "CYCLING"
        print_state()
        
        # Stop swing mixer
        main_mixer.voice[1].level = 0.0
        
        # Play extinguishing sound 
        extinguish_volume = 0.2
        main_mixer.voice[2].play(extinguish, loop=False)
        main_mixer.voice[2].level = extinguish_volume
        
        # Animate the blade out and fade hum sound out
        for p in reversed(range(0, blade_pixels, 2)):
            if p + 1 < blade_pixels:
                blade_led[p] = (0, 0, 0)
                blade_led[p + 1] = (0, 0, 0)
            else:
                blade_led[p] = (0, 0, 0)
            blade_led.show()
            extinguish_volume = min(max_hum_volume, (extinguish_volume + 0.021))
            main_mixer.voice[2].level = extinguish_volume
            hum_volume = max(0.0, (hum_volume - 0.022))
            main_mixer.voice[0].level = hum_volume
            time.sleep(0.01)
        
        time.sleep(1)    
        # Stop the sound
        i2s.stop()
        
        # Clear memory
        gc.collect()
        
        # Set the global state
        current_state = "STANDBY"
        print_state()


# == Main Loop == #
# Load profile
current_selection = config["save_state"]
load_profile(current_selection)
print_profile()
load_soundfont()

current_state = "STANDBY"
print_state()

# Begin the main loop
try:
    while True:
        # Track time delta
        time_current = time.monotonic()
        time_delta = time_current - time_previous
        time_previous = time_current

        # Saber is not ignitied
        if current_state == "STANDBY":
            # Show current profiles' color on board and crystal
            board_led.fill(color)
            board_led.show()

            blade_led[0] = color
            blade_led.show()

            # Poll both buttons
            poll_button_main()
            poll_button_aux()

        # Saber is ignitied
        if current_state == "ACTIVE":
            # Poll only main button
            poll_button_main()

            # Process gyroscope data
            gyro_rms = calculate_gyro_rms()
            gyro_filtered = lowpass_filter(gyro_rms, previous_gyro_filtered, lowpass_alpha)
            previous_gyro_filtered = gyro_filtered

            # If swinging detected
            if gyro_filtered > swing_threshold:
                # Accumulate swing and calculate it's strength
                accumulated_swing = accumulate_swing_angle(gyro_filtered, time_delta, accumulated_swing)
                swing_strength = calculate_swing_strength(gyro_filtered, swing_sharpness)

                # Modulate swinging hum sounds
                # Fade one way
                if accumulated_swing > transition_point_1:
                    swingh_volume, swingl_volume = do_crossfade(transition_region_1, transition_point_1)
                    swing_mixer.voice[0].level = swingh_volume
                    swing_mixer.voice[1].level = swingl_volume
                # Fade back to wrap around
                if accumulated_swing > transition_point_2:
                    swingl_volume, swingh_volume = do_crossfade(transition_region_2, transition_point_2)
                    swing_mixer.voice[0].level = swingh_volume
                    swing_mixer.voice[1].level = swingl_volume

                # Modulate main mixer volumes
                hum_volume = min(1.0, max(0.25, max_hum_volume - swing_strength))
                main_mixer.voice[0].level = hum_volume
                swing_volume = min(1.0, max(0.0, swing_strength))
                main_mixer.voice[1].level = swing_volume

            # Process accelerometer data

            # Check for clashing

            # if accel_filtered > clash_threshold:
                # do clash

            # If not swinging
            else:
                # Reset everything
                accumulated_swing = 0
                swing_strength = 0
                hum_volume = max_hum_volume
                swing_volume = 0.0
                swingh_volume = 0.0
                swingl_volume = 0.0

        #print(f'hum:{main_mixer.voice[0].level}, swing:{main_mixer.voice[1].level}, swingl:{swing_mixer.voice[1].level}, swingh:{swing_mixer.voice[0].level}')
        gc.collect()
        time.sleep(0.042)

except KeyboardInterrupt:
    print('Keyboard interrupt detected - Closing')
finally:
    i2s.deinit()
    i2c.deinit()
    spi.deinit()
    print('=== Pythosaber Version 1.0.0 "The Initiate" ===')
    print('=== FINISHED ===')