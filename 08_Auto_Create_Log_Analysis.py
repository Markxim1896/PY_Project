import os
import paramiko
import threading
import datetime
import re
import openai
import time

# ======================
# 1. 配置区域（可抽取到配置文件/环境变量中）
# ======================

# 设备 IP 列表文件
IPLIST_FILE = 'iplist.txt'

# SSH 登录凭据文件（第一行用户名，第二行密码）
CREDENTIALS_FILE = 'credentials.txt'

# 要执行的命令：抓取设备日志
COMMAND_LOG = 'terminal length 0 \n show log'

# 要执行的命令：抓取设备日志
COMMAND_DEVICE_NAME = 'show running-config | include hostname'

# AI 接口配置（⚠️ 注意：请勿将 API Key 硬编码在正式环境中！建议改用环境变量）
AI_BASE_URL = "https://logiq-service.logitech.io/openai/v1"
AI_API_KEY = "eyJpZCI6ICI4MGEzMTFmYy1hYzcwLTRhMDgtOTMwNy01YWUzM2NiMDJlNmEiLCAia2V5IjogIkVpV0RDREIzRnRuUjJEdjdnblpvUWciLCAiZXhwaXJlc19hdCI6IDE3ODU4MzA1NjIuNDA5MTYxfQ"

# AI 模型（根据您的服务支持情况调整）
AI_MODEL = "gpt-4o"

# 保存 AI 分析结果的目录
AI_ANALYSIS_DIR = 'AI_analysis'

# ======================
# 2. 初始化：读取设备列表和登录凭据
# ======================

# 检查并创建 AI_analysis 目录
if not os.path.exists(AI_ANALYSIS_DIR):
    os.makedirs(AI_ANALYSIS_DIR)

# 读取设备 IP 列表
try:
    with open(IPLIST_FILE, 'r') as f:
        device_ips = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    print(f"❌ 错误：找不到设备 IP 文件 {IPLIST_FILE}")
    exit(1)
except Exception as e:
    print(f"❌ 读取设备 IP 文件出错：{e}")
    exit(1)

# 读取 SSH 登录凭据
try:
    with open(CREDENTIALS_FILE, 'r') as f:
        creds = [line.strip() for line in f if line.strip()]
        if len(creds) < 2:
            raise ValueError("credentials.txt 至少需要包含用户名和密码两行")
        username, password = creds[0], creds[1]
except FileNotFoundError:
    print(f"❌ 错误：找不到凭据文件 {CREDENTIALS_FILE}")
    exit(1)
except Exception as e:
    print(f"❌ 读取凭据文件出错：{e}")
    exit(1)

# ======================
# 3. AI 客户端初始化
# ======================

client = openai.OpenAI(
    base_url=AI_BASE_URL,
    api_key=AI_API_KEY
)

# ======================
# 4. 定义：处理单个设备的函数（SSH + AI 分析）
# ======================

def process_device(ip):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log_content = None
    ai_result = None

    try:
        print(f"🔌 正在连接设备：{ip}")
        ssh.connect(hostname=ip, username=username, password=password, look_for_keys=False, allow_agent=False)

        # 打开一个交互式 Shell
        shell = ssh.invoke_shell()
        time.sleep(1)  # 等待 shell 初始化

        # 发送 show running-config | include hostname 命令
        shell.send(COMMAND_DEVICE_NAME + '\n')
        time.sleep(2)  # Wait for the command to complete
        # Read the output until the prompt (usually ends with '#')
        output = ''
        while not output.endswith('#'):
            output += shell.recv(65535).decode('utf-8')
        # Extract hostname from the output (e.g., "hostname Switch01")
        main_line = [line for line in output.splitlines() if 'hostname ' in line][0]
        devicename = main_line.split()[1]

        # 发送 show log 命令
        shell.send(COMMAND_LOG + '\n')
        time.sleep(3)  # 等待命令发出

        # 读取返回数据直到出现设备提示符（通常是 # 或 >）
        log_output = ''
        timeout = 10  # 最长等待 10 秒收集日志
        start_time = datetime.datetime.now()

        while (datetime.datetime.now() - start_time).seconds < timeout:
            if shell.recv_ready():
                part = shell.recv(65535).decode('utf-8', errors='ignore')
                log_output += part
                # 简单判断是否出现提示符，比如 # 或 >
                if '#' in part or '>' in part:
                    # 简单启发式：如果已经收到一定量数据，认为日志抓取完成
                    if len(log_output) > 100:
                        break
            else:
                time.sleep(0.5)

        log_content = log_output

        if not log_content or len(log_content.strip()) == 0:
            print(f"⚠️ 设备 {ip} 未返回有效日志内容")
            return

        print(f"✅ 成功获取设备 {ip} 的日志")

        # 调用 AI 分析该日志
        print(f"🤖 正在调用 AI 分析设备 {ip} 的日志...")
        user_prompt = f"以下是从网络设备抓取的系统日志内容，请分析其中可能的问题、异常、安全事件或优化建议：\n\n日志内容：\n{log_content}"

        completion = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            stream=False,
            max_tokens=1024
        )

        ai_result = completion.choices[0].message.content

        # 保存 AI 分析结果到文件
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        safe_ip = re.sub(r'[^\w\.-]', '_', ip)  # 避免文件名非法字符
        output_filename = f"{AI_ANALYSIS_DIR}/{devicename}_{safe_ip}_{current_date}_AI_Analysis.txt"

        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(f"=== 日志内容: ===\n {log_content} \n")
            f.write(f"=== 设备名称: {devicename} ===\n")
            f.write(f"=== 设备 IP: {ip} ===\n")
            f.write(f"=== AI 分析时间: {current_date} ===\n\n")
            f.write(ai_result)

        print(f"📄 AI 分析结果已保存到：{output_filename}")

    except paramiko.AuthenticationException:
        print(f"❌ 认证失败，无法连接设备：{ip}")
    except paramiko.SSHException as e:
        print(f"❌ SSH连接异常，设备：{ip}，错误：{e}")
    except Exception as e:
        print(f"❌ 处理设备 {ip} 时发生错误：{e}")
    finally:
        try:
            ssh.close()
        except:
            pass

# ======================
# 5. 主程序：多线程处理所有设备
# ======================

threads = []
for ip in device_ips:
    thread = threading.Thread(target=process_device, args=(ip,))
    thread.start()
    threads.append(thread)

for thread in threads:
    thread.join()

print("\n🎉 所有设备处理完成！AI 分析结果保存在文件夹：AI_analysis/")