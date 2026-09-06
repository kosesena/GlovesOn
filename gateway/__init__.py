"""
GlovesOn gateway paketi.

.env dosyasi burada okunuyor - alt modullerin herhangi biri import edilmeden
once. Onceden main.py load_dotenv()'i import satirlarindan SONRA cagiriyordu,
yani modul seviyesinde okunan her degisken (store'daki DATABASE_URL,
sap_client'taki SAP_BASE_URL) bos goruyordu. SAP_BASE_URL'in bos gorunmesi
sessiz ve pahali bir hataydi: gercek bir tenant'i gosterip mock'a yazmaya
devam etmek demekti.
"""

from dotenv import load_dotenv

load_dotenv()
