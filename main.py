import pyaudio
import numpy as np
import sacn
import time
import sys
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import argparse

maxValue = 2 ** 16


def senderSetup(ip):
    sender = sacn.sACNsender()
    sender.start()
    sender[1].destination = ip
    sender.activate_output(1)
    return sender


def parse_args(choices):
    parser = argparse.ArgumentParser(
        description="DMX WiFi Sender help", prog="DMX WiFi Sender"
    )
    parser.add_argument("--ip", help="Destination DMX server")
    parser.add_argument("--id", help="Index of the soundcard")
    parser.add_argument("--list", help="List available soundcards", action="store_true")
    parser.add_argument("--multi", help="Aplitude multiplier", default="1.5")
    parser.add_argument("--rr", help="Reverse Right Channel", action="store_true")
    parser.add_argument("--rl", help="Reverse Left Channel", action="store_true")
    parser.add_argument("-p", "--pixels", help="Length of strip", default=10)
    parser.add_argument("-f", "--frames", help="Frames for pyAudio", default=512)
    parser.add_argument("--fps", help="Frame Per Second (refresh rate)", default=30)
    return parser.parse_args()


class BuildDMX:
    def dict(data, previous_dmx, fps):
        dmx = {}
        peak = (
                int(np.abs(np.max(data)) - int(np.min(data)))
                / maxValue
                * pixels
                * float(args.multi)
        )
        for i in range(int(pixels / 2)):
            division = pixels / 6
            if i <= int(peak) and i <= int(pixels / 6) and peak > 0.1:
                dmx[i] = {
                    "r": int((i * (100 / division)) * 2.55),
                    "g": 255,
                    "b": 0,
                }

            elif int(peak) >= i > division and i <= (division * 2):
                dmx[i] = {
                    "r": 255,
                    "g": 255 - int(((i - division) * (100 / division)) * 2.55),
                    "b": 0,
                }
            elif int(peak) >= i > (division * 2):
                dmx[i] = {
                    "r": 255,
                    "g": 0,
                    "b": 0,
                }
            else:
                try:
                    dmx[i] = {
                        "r": int((previous_dmx[i]['r'] / fps) * (fps / 3)),
                        "g": int((previous_dmx[i]['g'] / fps) * (fps / 3)),
                        "b": int((previous_dmx[i]['b'] / fps) * (fps / 3))
                    }
                except LookupError:
                    dmx[i] = {
                        "r": 0,
                        "g": 0,
                        "b": 0,
                    }
        return dmx

    def tuple(dmx_dict, reverse):
        dmx_data = ()
        rgb = ()
        if reverse is False:
            for i in range(len(dmx_dict)):
                rgb = (
                    dmx_dict[i]["r"],
                    dmx_dict[i]["g"],
                    dmx_dict[i]["b"]
                )
                dmx_data = dmx_data + rgb
        elif reverse is True:
            for i in range(len(dmx_dict) - 1, -1, -1):
                rgb = (
                    dmx_dict[i]["r"],
                    dmx_dict[i]["g"],
                    dmx_dict[i]["b"]
                )
                dmx_data = dmx_data + rgb
        return dmx_data


def start_sequence(deviceid, loopback, channels, sampleRate, fps):
    stream = p.open(
        format=pyaudio.paInt16,
        channels=int(channels),
        rate=int(sampleRate),
        input=True,
        frames_per_buffer=defaultframes,
        input_device_index=int(deviceid),
        as_loopback=loopback,
    )
    old_left = {}
    old_right = {}
    while True:
        dmx_dict_left = {}
        dmx_dict_right = {}
        data = np.frombuffer(stream.read(1024), dtype=np.int16)
        data_left = data[0::2]
        data_right = data[1::2]
        (dmx_dict_left) = BuildDMX.dict(data_left, old_left, fps)
        (dmx_dict_right) = BuildDMX.dict(data_right, old_right, fps)
        dmx_tuple_left = BuildDMX.tuple(dmx_dict_left, args.rl)
        dmx_tuple_right = BuildDMX.tuple(dmx_dict_right, args.rr)
        sender[1].dmx_data = dmx_tuple_left + dmx_tuple_right
        time.sleep(1 / int(fps))
        old_left = dmx_dict_left
        old_right = dmx_dict_right


# devices = AudioUtilities.GetSpeakers()
# interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
# volume = cast(interface, POINTER(IAudioEndpointVolume))

def get_soundcards(p):
    soundcards = {}
    for i in range(0, p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if p.get_host_api_info_by_index(info["hostApi"])["index"] == 1:
            soundcards[i] = {
                "name": p.get_device_info_by_index(i)["name"],
                "outChannels": p.get_device_info_by_index(i)["maxOutputChannels"],
                "inChannels": p.get_device_info_by_index(i)["maxInputChannels"],
                "sampleRate": p.get_device_info_by_index(i)["defaultSampleRate"],
            }
            soundcards["default"] = p.get_host_api_info_by_index(info["hostApi"])[
                "defaultOutputDevice"
            ]
    return soundcards


if __name__ == "__main__":
    p = pyaudio.PyAudio()
    soundcardlist = get_soundcards(p)
    args = parse_args(soundcardlist)
    defaultframes = int(args.frames)
    pixels = int(args.pixels)
    if args.list is True:
        for i in soundcardlist:
            if not i == "default":
                if i == soundcardlist["default"]:
                    print(i, soundcardlist[i]["name"], "[DEFAULT]")
                else:
                    print(i, soundcardlist[i]["name"])
        sys.exit()
    elif args.ip is None:
        print("IP address required, use --help")
        sys.exit()
    try:
        if args.id is None:
            deviceid = soundcardlist["default"]
        else:
            deviceid = int(args.id)
        sender = sacn.sACNsender()
        sender.start()
        sender.activate_output(1)
        sender[1].destination = str(args.ip)
        if soundcardlist[deviceid]["outChannels"] > 0:
            loopback = True
            channels = soundcardlist[deviceid]["outChannels"]
        else:
            loopback = False
            channels = soundcardlist[deviceid]["inChannels"]
        start_sequence(
            deviceid,
            loopback,
            channels,
            soundcardlist[deviceid]["sampleRate"],
            args.fps,
        )
    except Exception as e:
        print("Exception:", e)
        sender.stop()
    except:
        sender.stop()
