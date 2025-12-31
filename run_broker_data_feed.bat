@echo off cd /d F:\Development\root\Kite\broker-data-feed 
call myenv\Scripts\activate.bat 
python main.py --symbols-from-db
pause