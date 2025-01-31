## Copyright (C) 2012-2013  Daniel Pavel
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License along
## with this program; if not, write to the Free Software Foundation, Inc.,
## 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import argparse as _argparse
import logging
import sys as _sys

from importlib import import_module
from traceback import extract_tb
from traceback import format_exc

import logitech_receiver.device as _device
import logitech_receiver.receiver as _receiver

from logitech_receiver.base import receivers
from logitech_receiver.base import receivers_and_devices

from solaar import NAME

logger = logging.getLogger(__name__)

#
#
#


def _create_parser():
    parser = _argparse.ArgumentParser(
        prog=NAME.lower(), add_help=False, epilog=f"For details on individual actions, run `{NAME.lower()} <action> --help`."
    )
    subparsers = parser.add_subparsers(title="actions", help="optional action to perform")

    sp = subparsers.add_parser("show", help="show information about devices")
    sp.add_argument(
        "device",
        nargs="?",
        default="all",
        help="device to show information about; may be a device number (1..6), a serial number, "
        'a substring of a device\'s name, or "all" (the default)',
    )
    sp.set_defaults(action="show")

    sp = subparsers.add_parser("probe", help="probe a receiver (debugging use only)")
    sp.add_argument(
        "receiver", nargs="?", help="select receiver by name substring or serial number when more than one is present"
    )
    sp.set_defaults(action="probe")

    sp = subparsers.add_parser("profiles", help="read or write onboard profiles", epilog="Only works on active devices.")
    sp.add_argument(
        "device",
        help="device to read or write profiles of; may be a device number (1..6), a serial number, "
        "a substring of a device's name",
    )
    sp.add_argument("profiles", nargs="?", help="file containing YAML dump of profiles")
    sp.set_defaults(action="profiles")

    sp = subparsers.add_parser(
        "config",
        help="read/write device-specific settings",
        epilog="Please note that configuration only works on active devices.",
    )
    sp.add_argument(
        "device",
        help="device to configure; may be a device number (1..6), a serial number, " "or a substring of a device's name",
    )
    sp.add_argument("setting", nargs="?", help="device-specific setting; leave empty to list available settings")
    sp.add_argument("value_key", nargs="?", help="new value for the setting or key for keyed settings")
    sp.add_argument("extra_subkey", nargs="?", help="value for keyed or subkey for subkeyed settings")
    sp.add_argument("extra2", nargs="?", help="value for subkeyed settings")
    sp.set_defaults(action="config")

    sp = subparsers.add_parser(
        "pair",
        help="pair a new device",
        epilog="The Logitech Unifying Receiver supports up to 6 paired devices at the same time.",
    )
    sp.add_argument(
        "receiver", nargs="?", help="select receiver by name substring or serial number when more than one is present"
    )
    sp.set_defaults(action="pair")

    sp = subparsers.add_parser("unpair", help="unpair a device")
    sp.add_argument(
        "device",
        help="device to unpair; may be a device number (1..6), a serial number, " "or a substring of a device's name.",
    )
    sp.set_defaults(action="unpair")

    return parser, subparsers.choices


_cli_parser, actions = _create_parser()
print_help = _cli_parser.print_help


def _receivers(dev_path=None):
    for dev_info in receivers():
        if dev_path is not None and dev_path != dev_info.path:
            continue
        try:
            r = _receiver.ReceiverFactory.create_receiver(dev_info)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[%s] => %s", dev_info.path, r)
            if r:
                yield r
        except Exception as e:
            logger.exception("opening " + str(dev_info))
            _sys.exit(f"{NAME.lower()}: error: {str(e)}")


def _receivers_and_devices(dev_path=None):
    for dev_info in receivers_and_devices():
        if dev_path is not None and dev_path != dev_info.path:
            continue
        try:
            if dev_info.isDevice:
                d = _device.DeviceFactory.create_device(dev_info)
            else:
                d = _receiver.ReceiverFactory.create_receiver(dev_info)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("[%s] => %s", dev_info.path, d)
            if d is not None:
                yield d
        except Exception as e:
            logger.exception("opening " + str(dev_info))
            _sys.exit(f"{NAME.lower()}: error: {str(e)}")


def _find_receiver(receivers, name):
    assert receivers
    assert name

    for r in receivers:
        if name in r.name.lower() or (r.serial is not None and name == r.serial.lower()):
            return r


def _find_device(receivers, name):
    assert receivers
    assert name

    number = None
    if len(name) == 1:
        try:
            number = int(name)
        except Exception:
            pass
        else:
            assert not (number < 0)
            if number > 6:
                number = None

    for r in receivers:
        if not r.isDevice:  # look for nth device of receiver
            if number:
                dev = r[number]
                if dev:
                    yield dev
            count = r.count()
        else:  # wired device, make a device list from it
            r.ping()
            r = [r]
            count = 1

        for dev in r:
            if (
                name == dev.serial.lower()
                or name == dev.codename.lower()
                or name == str(dev.kind).lower()
                or name in dev.name.lower()
            ):
                yield dev
            count -= 1
            if not count:
                break


#    raise Exception("no device found matching '%s'" % name)


def run(cli_args=None, hidraw_path=None):
    if cli_args:
        action = cli_args[0]
        args = _cli_parser.parse_args(cli_args)
    else:
        args = _cli_parser.parse_args()
        # Python 3 has an undocumented 'feature' that breaks parsing empty args
        # http://bugs.python.org/issue16308
        if "cmd" not in args:
            _cli_parser.print_usage(_sys.stderr)
            _sys.stderr.write(f"{NAME.lower()}: error: too few arguments\n")
            _sys.exit(2)
        action = args.action
    assert action in actions

    try:
        if action == "show" or action == "probe" or action == "config" or action == "profiles":
            c = list(_receivers_and_devices(hidraw_path))
        else:
            c = list(_receivers(hidraw_path))
        if not c:
            raise Exception(
                'No supported device found.  Use "lsusb" and "bluetoothctl devices Connected" to list connected devices.'
            )
        m = import_module("." + action, package=__name__)
        m.run(c, args, _find_receiver, _find_device)
    except AssertionError:
        tb_last = extract_tb(_sys.exc_info()[2])[-1]
        _sys.exit("%s: assertion failed: %s line %d" % (NAME.lower(), tb_last[0], tb_last[1]))
    except Exception:
        _sys.exit(f"{NAME.lower()}: error: {format_exc()}")
