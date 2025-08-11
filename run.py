#!/usr/bin/env python3
"""
Quick start script for Streamlit Materials
"""

import subprocess
import sys
import os

def check_requirements():
    """Check if required packages are installed"""
    try:
        import streamlit
        import pandas
        import numpy
        return True
    except ImportError:
        return False

def install_requirements():
    """Install requirements if needed"""
    if not check_requirements():
        print("Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    """Main function to run the Streamlit app"""
    print("🚀 Starting Streamlit Materials...")
    
    # Install requirements if needed
    install_requirements()
    
    # Run the Streamlit app
    print("📱 Launching Streamlit application...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])

if __name__ == "__main__":
    main()
