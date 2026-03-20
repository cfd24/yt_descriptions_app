import gspread
from oauth2client.service_account import ServiceAccountCredentials

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
gc = gspread.authorize(creds)
sheet = gc.open("YT_Scraper_DB").sheet1

data = sheet.get_all_values()
for i, row in enumerate(data[:10]):
    print(f"Row {i}: {row}")
