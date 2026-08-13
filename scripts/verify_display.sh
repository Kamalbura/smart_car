#!/bin/bash
echo "Checking Display Setup..."

if pgrep Xorg >/dev/null; then
    echo "✅ Xorg (X11) is running."
else
    echo "❌ Xorg is NOT running."
fi

if pgrep anydesk >/dev/null; then
    echo "✅ AnyDesk is running."
else
    echo "❌ AnyDesk is NOT running."
fi

if [ -f /etc/X11/xorg.conf.d/99-fbturbo.conf ]; then
    echo "✅ fbturbo config found."
else
    echo "❌ fbturbo config missing."
fi

DRIVER_STATUS=$(dpkg -l | grep xserver-xorg-video-fbturbo)
if [ -n "$DRIVER_STATUS" ]; then
    echo "✅ fbturbo driver installed."
else
    echo "❌ fbturbo driver NOT installed."
fi

echo "Current Display Manager: $(cat /etc/X11/default-display-manager)"
