import requests_h2

try:
  response = requests_h2.get("https://www.instagram.com/", http2=True)
  print(response.text[:500])
except requests.exceptions.ConnectionError:
  print("pas de connexion")