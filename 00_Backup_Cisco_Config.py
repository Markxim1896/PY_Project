import paramiko
import time
import os
import threading
import datetime

# Check and create the config folder if it doesn't exist
if not os.path.exists('config'):
    os.makedirs('config')

# Read IP addresses from iplist.txt
try:
    with open('iplist.txt', 'r') as file:
        ip_addresses = file.read().splitlines()
except FileNotFoundError:
    print("Error: iplist.txt not found.")
    exit(1)

# Read credentials from credentials.txt
try:
    with open('credentials.txt', 'r') as file:
        credentials = file.read().splitlines()
        username = credentials[0]
        password = credentials[1]
except FileNotFoundError:
    print("Error: credentials.txt not found.")
    exit(1)

# Define commands to execute
commands = [
    'terminal length 0',
    'show version',
    'show inventory',
    'show ip interface brief',
    'show running-config'
]

# Function to handle SSH connection and command execution for a single IP
def process_ip(ip):
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        # Connect to the switch
        ssh_client.connect(hostname=ip, username=username, password=password, look_for_keys=False, allow_agent=False)
        # Create a shell session
        shell = ssh_client.invoke_shell()
        # Get the switch hostname by sending the command and reading the output
        shell.send('show running-config | include hostname\n')
        time.sleep(2)  # Wait for the command to complete
        # Read the output until the prompt (usually ends with '#')
        output = ''
        while not output.endswith('#'):
            output += shell.recv(65535).decode('utf-8')
        # Extract hostname from the output (e.g., "hostname Switch01")
        hostname_line = [line for line in output.splitlines() if 'hostname ' in line][0]
        hostname = hostname_line.split()[1]
        print(f"成功连接到 {hostname}_{ip}")
        # Add date to filename
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"config/{hostname}_{ip}_{current_date}_Output.txt"
        with open(filename, 'w') as output_file:
            for command in commands:
                shell.send(command + '\n')
                time.sleep(2)  # Wait for the command to complete
                # Read the output until the prompt (usually ends with '#')
                output = ''
                while not output.endswith('#'):
                    output += shell.recv(65535).decode('utf-8')
                # Write command and output to the file
                output_file.write(f"=== Command: {command} ===\n\n")
                output_file.write(output + "\n\n")
        # Close the shell session
        shell.close()
    except paramiko.AuthenticationException:
        print(f"认证失败: {ip}")
    except paramiko.SSHException as ssh_ex:
        print(f"SSH连接失败: {ip} - {ssh_ex}")
    except Exception as ex:
        print(f"发生错误: {ip} - {ex}")
    finally:
        # Ensure SSH connection is closed
        ssh_client.close()

# Create and start threads for each IP address
threads = []
for ip in ip_addresses:
    thread = threading.Thread(target=process_ip, args=(ip,))
    thread.start()
    threads.append(thread)

# Wait for all threads to complete
for thread in threads:
    thread.join()

print("所有设备处理完成。")
