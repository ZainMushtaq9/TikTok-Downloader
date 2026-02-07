#!/bin/bash

# Video Downloader - Startup Script
# This script sets up and starts the video downloader application

echo "================================================"
echo "  Video Downloader - Production Setup"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "\n${YELLOW}Checking Python version...${NC}"
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"

# Check if FFmpeg is installed
echo -e "\n${YELLOW}Checking FFmpeg...${NC}"
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✓ FFmpeg is installed${NC}"
else
    echo -e "${RED}✗ FFmpeg not found${NC}"
    echo "Installing FFmpeg..."
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update
        sudo apt install -y ffmpeg
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ffmpeg
    else
        echo -e "${RED}Please install FFmpeg manually${NC}"
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "\n${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "\n${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install/upgrade pip
echo -e "\n${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "\n${YELLOW}Installing Python dependencies...${NC}"
pip install -r requirements.txt

# Create downloads directory
echo -e "\n${YELLOW}Creating downloads directory...${NC}"
mkdir -p /tmp/downloads
chmod 777 /tmp/downloads
echo -e "${GREEN}✓ Downloads directory created${NC}"

# Display configuration
echo -e "\n================================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "================================================"
echo ""
echo "Configuration:"
echo "  - API Server: http://localhost:8000"
echo "  - Downloads: /tmp/downloads"
echo "  - Concurrent Workers: 4"
echo ""
echo "================================================"

# Ask user if they want to start the server
read -p "Start the server now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "\n${GREEN}Starting server...${NC}"
    echo "Press Ctrl+C to stop"
    echo ""
    python3 main.py
else
    echo -e "\n${YELLOW}To start the server later, run:${NC}"
    echo "  source venv/bin/activate"
    echo "  python3 main.py"
fi
