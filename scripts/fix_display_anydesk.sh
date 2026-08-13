#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color


echo -e "${GREEN}Starting Display and AnyDesk Fixer...${NC}"

# --- 1. Fix "display_server_not_supported" (Switch to X11) ---
echo -e "${YELLOW}[1/3] Checking Display Server Protocol...${NC}"

if command -v raspi-config >/dev/null; then
    echo "raspi-config found. Attempting to switch to X11 (Xorg)..."
    # 'nonint do_wayland W1' switches to X11
    # 'nonint do_wayland W2' switches to Wayland
    sudo raspi-config nonint do_wayland W1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully configured system to use X11.${NC}"
    else
        echo -e "${RED}Failed to switch to X11 via raspi-config.${NC}"
    fi
else
    echo "raspi-config not found. Checking for GDM3 config..."
    if [ -f /etc/gdm3/daemon.conf ]; then
        sudo sed -i 's/#WaylandEnable=false/WaylandEnable=false/' /etc/gdm3/daemon.conf
        echo -e "${GREEN}Disabled Wayland in /etc/gdm3/daemon.conf${NC}"
    elif [ -f /etc/gdm3/custom.conf ]; then
        sudo sed -i 's/#WaylandEnable=false/WaylandEnable=false/' /etc/gdm3/custom.conf
        echo -e "${GREEN}Disabled Wayland in /etc/gdm3/custom.conf${NC}"
    else
        echo -e "${YELLOW}Could not find standard Wayland config to disable. If you are on a Pi, ensure raspi-config is installed.${NC}"
    fi
fi

# --- 2. AnyDesk Setup ---
echo -e "${YELLOW}[2/3] Verifying AnyDesk...${NC}"
if command -v anydesk >/dev/null; then
    echo "AnyDesk is installed."
    # Ensure service is running
    sudo systemctl enable anydesk
    sudo systemctl start anydesk
    echo -e "${GREEN}AnyDesk service started.${NC}"
    echo "If you need to set a password for unattended access, run:"
    echo "  echo my_new_password | sudo anydesk --set-password"
else
    echo -e "${RED}AnyDesk is not installed.${NC}"
    echo "To install: sudo apt update && sudo apt install anydesk (or download .deb from anydesk.com)"
fi

# --- 3. Waveshare Display Setup ---
echo -e "${YELLOW}[3/3] Checking Waveshare Display Drivers...${NC}"
LCD_SHOW_DIR="$(pwd)/third_party/LCD-show"

if [ -d "$LCD_SHOW_DIR" ]; then
    echo "Found LCD-show drivers in $LCD_SHOW_DIR"
    
    # Make sure scripts are executable
    chmod +x "$LCD_SHOW_DIR"/*-show
    
    echo -e "${GREEN}Drivers are ready.${NC}"
    echo -e "${YELLOW}IMPORTANT: Installing the display driver will REBOOT your Raspberry Pi immediately.${NC}"
    echo "To install the 3.5 inch display driver (common for this project), run this command manually:"
    echo ""
    echo -e "  ${GREEN}cd third_party/LCD-show && sudo ./LCD35-show${NC}"
    echo ""
    echo "If you have a different model (e.g. HDMI, 4 inch), choose the appropriate script in that directory."
else
    echo -e "${RED}LCD-show directory not found in third_party/.${NC}"
    echo "Please clone the driver repo: git clone https://github.com/waveshare/LCD-show.git third_party/LCD-show"
fi

echo -e "${GREEN}Setup script completed.${NC}"
echo "Please reboot your system for the X11 switch to take effect (if you aren't running the LCD installer immediately)."
