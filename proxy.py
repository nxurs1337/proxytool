import threading
import requests
import queue
import time
import os
import sys
from colorama import Fore, Style, init

init(autoreset=True)

proxy_counters = {
    "http": 0,
    "https": 0,
    "socks4": 0,
    "socks5": 0
}

country_codes = {
    "Tümü": "",
    "Türkiye": "TR",
    "ABD": "US",
    "Almanya": "DE",
    "Fransa": "FR",
    "Hollanda": "NL",
    "İngiltere": "GB",
    "Rusya": "RU",
    "Japonya": "JP",
    "Kanada": "CA",
    "Avustralya": "AU"
}

def fetch_real_proxies(proxy_type, country_code):
    all_proxies = []
    
    # --- Source 1: Proxyscrape ---
    proxyscrape_url = f"https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&proxy_format=ipport&format=text&protocol={proxy_type}"
    if country_code:
        proxyscrape_url += f"&country={country_code}"
    try:
        resp = requests.get(proxyscrape_url, timeout=10)
        if resp.status_code == 200:
            ps_list = [p.strip() for p in resp.text.strip().split('\n') if p.strip()]
            all_proxies.extend(ps_list)
    except:
        pass

    # --- Source 2: iplocate (GitHub) ---
    # Github lists: all-proxies.txt, http.txt, https.txt, socks4.txt, socks5.txt
    github_map = {
        "all": "all-proxies.txt",
        "http": "http.txt",
        "https": "https.txt",
        "socks4": "socks4.txt",
        "socks5": "socks5.txt"
    }
    
    if proxy_type in github_map:
        github_url = f"https://raw.githubusercontent.com/iplocate/free-proxy-list/main/{github_map[proxy_type]}"
        try:
            resp = requests.get(github_url, timeout=10)
            if resp.status_code == 200:
                gh_list = [p.strip() for p in resp.text.strip().split('\n') if p.strip()]
                all_proxies.extend(gh_list)
        except:
            pass

    # --- De-duplicate and Return ---
    final_proxies = list(set(all_proxies))
    return final_proxies

def save_proxies(proxy_type, proxies):
    idx = 1
    while os.path.exists(f"{proxy_type}_proxy_{idx}.txt"):
        idx += 1
    
    filename = f"{proxy_type}_proxy_{idx}.txt"
    with open(filename, "w") as f:
        for proxy in proxies:
            f.write(proxy + "\n")
    return filename

def run_generator():
    print(f"\n{Fore.CYAN}--- Proxy Çekme ---")
    print("1. http")
    print("2. https")
    print("3. socks4")
    print("4. socks5")
    print("5. mixed")
    
    type_choice = input("\nProxy türü seçin (1-5): ").strip()
    types = ["http", "https", "socks4", "socks5", "all"]
    if type_choice not in ["1", "2", "3", "4", "5"]:
        print(f"{Fore.RED}[!] Geçersiz seçim.")
        return
    proxy_type = types[int(type_choice)-1]
    
    try:
        count = int(input("Kaç adet proxy çekilsin? ").strip())
    except ValueError:
        print(f"{Fore.RED}[!] Geçersiz sayı.")
        return

    print("\nÜlkeler:")
    countries = list(country_codes.keys())
    for i, country in enumerate(countries, 1):
        print(f"{i}. {country}")
    
    try:
        country_choice = int(input("\nÜlke seçin : ").strip())
        country_name = countries[country_choice-1]
        country_code = country_codes[country_name]
    except (ValueError, IndexError):
        print(f"{Fore.YELLOW}[!] Geçersiz seçim, varsayılan (Tümü) seçildi.")
        country_code = ""

    print(f"\n{Fore.BLUE}[*] {proxy_type} proxyler alınıyor...")
    proxies = fetch_real_proxies(proxy_type, country_code)
    
    if proxies:
        selected = proxies[:count]
        filename = save_proxies(proxy_type, selected)
        print(f"{Fore.GREEN}[OK] {len(selected)} proxy kaydedildi -> {filename}")
    else:
        print(f"{Fore.RED}[!] Proxy bulunamadı.")

valid_proxies = [] 
lock = threading.Lock()
q = queue.Queue()

def get_anonymity(headers, proxy_ip):
    forwarded = headers.get("X-Forwarded-For", "")
    if forwarded and proxy_ip not in forwarded:
        return "Transparent"
    anon_headers = ["Via", "Proxy-Connection", "X-Proxy-ID", "X-Real-IP"]
    if any(h in headers for h in anon_headers):
        return "Anonymous"
    return "Elite"

def check_proxy():
    while not q.empty():
        try:
            proxy = q.get_nowait()
        except queue.Empty:
            break
            
        working_type = None
        working_country = "Unknown"
        working_ping = 0
        working_anon = "Unknown"
        
        protocols = ["http", "socks5", "socks4"]
        for p_type in protocols:
            proxies = {
                "http": f"{p_type}://{proxy}",
                "https": f"{p_type}://{proxy}"
            }
            start_time = time.time()
            try:
                geo_resp = requests.get("http://ip-api.com/json/", proxies=proxies, timeout=5)
                if geo_resp.status_code == 200:
                    geo_data = geo_resp.json()
                    if geo_data.get("status") == "success":
                        working_ping = int((time.time() - start_time) * 1000)
                        working_type = p_type
                        working_country = geo_data.get("country", "Unknown")
                        proxy_ip = geo_data.get("query", "")
                        
                        try:
                            anon_resp = requests.get("http://httpbin.org/get", proxies=proxies, timeout=5)
                            headers = anon_resp.json().get("headers", {}) if anon_resp.status_code == 200 else {}
                            working_anon = get_anonymity(headers, proxy_ip)
                        except:
                            working_anon = "Unknown"
                        break 
            except:
                continue

        if working_type:
            color = Fore.GREEN if working_ping < 1000 else Fore.YELLOW
            with lock:
                valid_proxies.append({
                    "proxy": proxy, 
                    "type": working_type,
                    "ping": working_ping, 
                    "country": working_country, 
                    "anonymity": working_anon
                })
                print(f"{color}[+] {proxy:<21} | {working_type:<6} | {working_country:<12} | Ping: {working_ping:>4}ms | Anon: {working_anon}")
        else:
            print(f"{Fore.RED}[-]{proxy:<21} | Zaman Asimi/Hata")
            
        q.task_done()

def run_checker():
    global valid_proxies
    valid_proxies = []
    
    print(f"\n{Fore.CYAN}--- Proxy Checker ---")
    txt_files = [f for f in os.listdir() if f.endswith(".txt")]
    if txt_files:
        print("Mevcut dosyalar:")
        for f in txt_files:
            print(f" - {f}")
    
    proxy_file = input("\nKontrol edilecek dosya adı: ").strip()
    if not os.path.exists(proxy_file):
        print(f"{Fore.RED}[!] Dosya bulunamadı!")
        return

    try:
        with open(proxy_file, "r") as f:
            proxy_list = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"{Fore.RED}[!] Dosya okuma hatası: {e}")
        return

    if not proxy_list:
        print(f"{Fore.RED}[!] Dosya boş.")
        return

    print(f"\n{Fore.BLUE}[*] {len(proxy_list)} proxy kontrol ediliyor (50 thread)...")
    for p in proxy_list:
        q.put(p)

    thread_list = []
    start_time = time.time()
    for _ in range(50):
        t = threading.Thread(target=check_proxy, daemon=True)
        t.start()
        thread_list.append(t)

    for t in thread_list:
        t.join()

    if valid_proxies:
        print(f"\n{Fore.CYAN}--- Kaydet ---")
        print("1. Tüm çalişanlari kaydet")
        print("2. Sadece 1000ms alti kaydet")
        save_mode = input("Seçiminiz (1/2): ").strip()

        if save_mode == "2":
            to_save = [p for p in valid_proxies if p["ping"] < 1000]
            filename = "1000msalti.txt"
        else:
            to_save = valid_proxies
            filename = "calisanlar.txt"

        if to_save:
            print("\nkaydetme sekli seciniz")
            print("1. Sadece IP:Port")
            print("2. Captureli")
            capture_choice = input("Seçiminiz (1/2): ").strip()
            
            if capture_choice == "2":
                filename = filename.replace(".txt", "_capture.txt")

            with open(filename, "w", encoding="utf-8") as f:
                for p in to_save:
                    if capture_choice == "2":
                        f.write(f"{p['proxy']:<21} | {p['type']:<6} | {p['country']:<12} | Ping: {p['ping']:>4}ms | Anon: {p['anonymity']}\n")
                    else:
                        f.write(p["proxy"] + "\n")
            print(f"\n{Fore.GREEN}[OK] Toplam kaydedilen: {len(to_save)} -> {filename}")
        else:
            print(f"\n{Fore.YELLOW}[!] Kaydedilecek kriterlere uygun proxy bulunamadı.")
    else:
        print(f"\n{Fore.RED}[!] Geçerli proxy bulunamadı.")

    print(f"{Fore.BLUE}[*] Süre: {round(time.time() - start_time, 2)} sn")

def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n" + Fore.MAGENTA + "-"*48)
        print(Fore.MAGENTA + "        neurs proxy generator + checker      ")
        print(Fore.MAGENTA + "-"*48)
        print("1. Proxy Çek")
        print("2. Proxy Kontrol Et")
        print("3. bitti aminakoyum")
        
        choice = input(f"\n{Fore.WHITE}Seçiminiz: ").strip()
        
        if choice == "1":
            run_generator()
        elif choice == "2":
            run_checker()
        elif choice == "3":
            print(f"{Fore.YELLOW}bb")
            sys.exit()
        else:
            print(f"{Fore.RED}[!] Geçersiz seçim.")

def show_startup_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    header = rf"""{Fore.MAGENTA}       .__                    _______________  _____________                .__  .__               
  _____|__| ____   ____  ____ \_____  \   _  \/_   \______  \   ____   ____ |  | |__| ____   ____  
 /  ___/  |/    \_/ ___\/ __ \ /  ____/  /_\  \|   |   /    /  /  _ \ /    \|  | |  |/    \_/ __ \ 
 \___ \|  |   |  \  \__\  ___//       \  \_/   \   |  /    /  (  <_> )   |  \  |_|  |   |  \  ___/ 
/____  >__|___|  /\___  >___  >_______ \_____  /___| /____/ /\ \____/|___|  /____/__|___|  /\___  >
     \/        \/     \/    \/        \/     \/             \/            \/             \/     \/ 

{Fore.WHITE}since2017.online 

Telegram @neurss 

CrackTurkey @neursxd 

CheatGlobal @Neurs"""
    print(header)
    time.sleep(5)

if __name__ == "__main__":
    try:
        show_startup_header()
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}ctrl c basma mal")
        sys.exit()
