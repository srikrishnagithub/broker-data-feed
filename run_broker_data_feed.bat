@echo off cd /d D:\Development\broker_data_feed 
call venv\Scripts\activate.bat 
python main.py --symbols-from-db
pause