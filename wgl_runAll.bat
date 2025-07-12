REM This is the Waconia Batch file, scheduled on the BeeLink server.

SET PERL5LIB=C:\Users\Jim\Documents\webcontent\waconia

C:\Strawberry\perl\bin\perl.exe "C:\Users\Jim\Documents\webcontent\waconia\wgl_perl_hanford.pl"
C:\Strawberry\perl\bin\perl.exe "C:\Users\Jim\Documents\webcontent\waconia\wgl_perl_noaa.pl"

py "C:\Users\Jim\Documents\webcontent\waconia\wgl_python_aw.py"
py "C:\Users\Jim\Documents\webcontent\waconia\wgl_python_meso.py"