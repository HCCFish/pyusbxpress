# Using pyusbxpress on Linux

The libusb backend runs on Linux unchanged; only device permissions need to
be set up.

## 1. Check that the device is visible

```console
lsusb | grep -i 10c4
```

A USBXpress device typically shows up as `10c4:ea61`.  If it does not,
check the cable and that the firmware is running.

## 2. Allow access without root

By default only root may open USB devices.  Add a udev rule:

```console
sudo tee /etc/udev/rules.d/60-usbxpress.rules >/dev/null <<'EOF'
# USBXpress devices (VID 10c4). Adjust the PID if your firmware uses another one.
SUBSYSTEM=="usb", ATTR{idVendor}=="10c4", ATTR{idProduct}=="ea61", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then unplug and replug the device (or power cycle the board).

Alternatively add your user to a group that owns the device node and use
`MODE="0660", GROUP="plugdev"` (Debian/Ubuntu) or the distribution's
equivalent.

Verify:

```console
usbxpress list
usbxpress info
```

## 3. No kernel driver conflict

USBXpress devices declare a vendor-specific interface (`0xFF`), so no kernel
driver claims them and libusb can use the interface directly.  If a driver
does hold the device (check with `lsusb -t`), unload it or add it to the
udev rule with `ATTRS{driver}=="..."` exclusions.

## 4. Testing from Windows via WSL2 (no extra hardware)

If you develop on Windows, you can exercise the Linux code path with WSL2
and `usbipd-win`:

```powershell
# Windows, once: install usbipd-win (https://github.com/dorssel/usbipd-win)
usbipd list
usbipd bind --busid <BUSID>       # requires admin, once per device
usbipd attach --wsl --busid <BUSID>
```

```console
# inside WSL
sudo apt install -y python3-pip
pip install pyusbxpress
usbxpress list
usbxpress info
```

Notes:

- The device must be bound to WinUSB on the Windows side (Zadig) before it
  can be shared with WSL2.
- `usbipd attach` lasts until the device is unplugged or the WSL instance is
  restarted.
- Inside WSL the udev rule above applies as well if you do not run as root.

## 5. Reporting results

Please open an issue with:

- `uname -a`, distribution and kernel version,
- `lsusb -v -d 10c4:ea61` (or at least the interface and endpoint
  descriptors),
- the output of `usbxpress info` and of one `usbxpress monitor` run.
