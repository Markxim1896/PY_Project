import os
import csv
from datetime import datetime
from netmiko import ConnectHandler

# ===== 1. Create output directory =====
output_dir = "Mac_location"
os.makedirs(output_dir, exist_ok=True)
today_date = datetime.now().strftime("%Y-%m-%d")  # e.g. 2025-09-11
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # e.g. 2025-09-11 09:25:01
print(f"📅 Today's date: {today_date}, Check time stamp: {current_time}")

csv_filename = f"Check_location_{today_date}.csv"
output_csv_path = os.path.join(output_dir, csv_filename)

# ===== 2. Read switch IP list =====
with open("iplist.txt", "r") as f:
    device_ips = [line.strip() for line in f if line.strip()]

# ===== 3. Read login credentials =====
with open("credentials.txt", "r") as f:
    lines = f.readlines()
    username = lines[0].strip()
    password = lines[1].strip()

# ===== 4. Read interface_location.csv (optional) =====
interface_location_map = {}  # Format: {Device_name: {interface: location}}

try:
    with open("interface_location.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dev = row["Device_name"].strip()
            intf = row["interface"].strip()
            loc = row["location"].strip()
            if dev not in interface_location_map:
                interface_location_map[dev] = {}
            interface_location_map[dev][intf] = loc
    print("✅ Loaded interface_location.csv. Location mapping will be applied.")
except FileNotFoundError:
    print("⚠️ interface_location.csv not found. Location will be set to 'Unknown'.")
    interface_location_map = {}

# ===== 5. Define device connection template =====
def get_device_params(ip):
    return {
        'device_type': 'cisco_ios',
        'host': ip,
        'username': username,
        'password': password,
        'secret': '',  # Optional enable password
        'timeout': 10,
    }

# ===== 6. Main logic: connect, extract MACs & interfaces =====
all_mac_records = []

for ip in device_ips:
    print(f"\n🔌 Connecting to switch IP: {ip}")
    try:
        device = get_device_params(ip)
        with ConnectHandler(**device) as conn:
            prompt = conn.find_prompt()
            device_name = prompt.replace("#", "").strip()
            print(f"✅ Device name: {device_name}")

            command = "show mac address-table dynamic | include Gi"
            output = conn.send_command(command)

            for raw_line in output.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                mac = None
                intf = None

                parts = line.split()
                for i, part in enumerate(parts):
                    if '.' in part and len(part.split('.')) == 3:
                        subparts = part.split('.')
                        if all(1 <= len(x) <= 4 for x in subparts):
                            candidate_mac = part
                            remaining = parts[i+1:]
                            if remaining:
                                for candidate_intf in remaining:
                                    candidate_intf = candidate_intf.strip(',')
                                    if 'Gi' in candidate_intf or 'GigabitEthernet' in candidate_intf:
                                        mac = candidate_mac
                                        if 'GigabitEthernet' in candidate_intf:
                                            intf = candidate_intf.replace('GigabitEthernet', 'Gi')
                                        else:
                                            intf = candidate_intf
                                        break
                                if mac and intf:
                                    break

                if mac and intf:
                    location = "Unknown"
                    if device_name in interface_location_map and intf in interface_location_map[device_name]:
                        location = interface_location_map[device_name][intf]

                    record = {
                        "Device_name": device_name,
                        "MAC_Address": mac,
                        "Interface": intf,
                        "Location": location,
                        "Check time": current_time
                    }
                    all_mac_records.append(record)
                    print(f"🔗 Extracted -> Device: {device_name}, MAC: {mac}, Interface: {intf}, Location: {location}, Time: {current_time}")
                else:
                    print(f"⚠️ Could not parse: {line}")

    except Exception as e:
        print(f"❌ Error processing device {ip}: {e}")

# ===== 7. Write to CSV (date-based filename, append mode) =====
if all_mac_records:
    headers = ["Device_name", "MAC_Address", "Interface", "Location", "Check time"]

    file_exists = os.path.isfile(output_csv_path)

    with open(output_csv_path, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()  # Write header only if file is new
        writer.writerows(all_mac_records)

    print(f"✅ Data saved to: {output_csv_path} (Appended if existing, new file if not)")
else:
    print("\n❌ No MAC records were extracted. Please check device connections or command output.")