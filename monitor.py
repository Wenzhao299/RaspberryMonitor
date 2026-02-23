import pygame
import psutil
import os
import time
import socket
import datetime
import subprocess

# --- 1. 配置区域 ---
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
FPS = 1
DATA_UPDATE_INTERVAL = 1.0
SERVICE_CHECK_INTERVAL = 15.0  # 服务状态每 15 秒检查一次即可

# 底部监控的服务
MONITORED_SERVICES = [
    {"name": "SSH",  "service": "ssh"},
    {"name": "VNC",  "service": "vncserver-x11-serviced"},
    {"name": "Clash",  "service": "clash"},
    {"name": "Frpc",  "service": "frpc"},
    {"name": "API",  "service": "cliproxyapi.service", "is_user": True},
    {"name": "Jarvis",  "service": "openclaw-gateway.service", "is_user": True},
    {"name": "News",  "service": "daily-hot-api", "is_user": True}
]

# --- 全局颜色变量初始化 (稍后由 set_theme 填充) ---
COLOR_BG = (0, 0, 0)
COLOR_PANEL_BG = (0, 0, 0)
COLOR_ACCENT = (0, 0, 0)
COLOR_TEXT_VAL = (0, 0, 0)
COLOR_TEXT_LABEL = (0, 0, 0)
COLOR_WARN = (0, 0, 0)
COLOR_DANGER = (0, 0, 0)
COLOR_OK = (0, 0, 0)
COLOR_BORDER = (0, 0, 0)

# 颜色反转配置
THEME_SWITCH_INTERVAL = 3600  # 3600秒 = 1小时
last_theme_switch_time = 0    # 上次切换时间
is_light_theme = True        # 当前是否为亮色模式

def set_theme(is_light):
    global COLOR_BG, COLOR_PANEL_BG, COLOR_ACCENT, COLOR_TEXT_VAL
    global COLOR_TEXT_LABEL, COLOR_WARN, COLOR_DANGER, COLOR_OK, COLOR_BORDER
    
    if is_light:
        # === 亮色模式 (Light Theme) - 白底黑字 ===
        COLOR_BG = (250, 250, 250)
        COLOR_PANEL_BG = (235, 235, 235)
        COLOR_ACCENT = (0, 100, 200)      # 深蓝色，在白底上对比度好
        COLOR_TEXT_VAL = (20, 20, 20)     # 近乎黑色
        COLOR_TEXT_LABEL = (80, 80, 80)   # 深灰色
        COLOR_WARN = (220, 120, 0)
        COLOR_DANGER = (220, 40, 40)
        COLOR_OK = (0, 180, 60)
        COLOR_BORDER = (180, 180, 180)
    else:
        # === 暗色模式 (Dark Theme) - 原版黑底 ===
        COLOR_BG = (10, 10, 15)
        COLOR_PANEL_BG = (20, 25, 35)
        COLOR_ACCENT = (0, 255, 230)      # 青色荧光
        COLOR_TEXT_VAL = (240, 240, 240)  # 白色
        COLOR_TEXT_LABEL = (120, 130, 140)
        COLOR_WARN = (255, 180, 0)
        COLOR_DANGER = (255, 50, 50)
        COLOR_OK = (50, 255, 50)
        COLOR_BORDER = (50, 60, 80)

# 初始化为暗色主题
set_theme(is_light_theme)
last_theme_switch_time = time.time()

# --- 2. 初始化 ---
# os.environ["SDL_FBDEV"] = "/dev/fb1" 
# pygame.init()  <-- 删除这行
pygame.display.init()  # 只初始化显示
pygame.font.init()     # 只初始化字体

try:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
except:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

pygame.mouse.set_visible(False)
clock = pygame.time.Clock()

# --- 3. 字体加载 ---
try:
    font_header = pygame.font.SysFont("dejavusans", 22, bold=True)
    font_date = pygame.font.SysFont("dejavusans", 22, bold=True)
    font_val = pygame.font.SysFont("dejavusans", 16, bold=True)
    font_label = pygame.font.SysFont("dejavusans", 14)
    font_mini = pygame.font.SysFont("dejavusans", 14)
except:
    font_header = pygame.font.SysFont(None, 22)
    font_date = pygame.font.SysFont(None, 22)
    font_val = pygame.font.SysFont(None, 16)
    font_label = pygame.font.SysFont(None, 14)
    font_mini = pygame.font.SysFont(None, 14)

# --- 4. 数据结构类 ---
class SystemData:
    def __init__(self):
        self.cpu_pct = 0
        self.ram_pct = 0
        self.ram_used = 0
        self.ram_total = 0
        self.disk_pct = 0
        self.disk_used = 0
        self.disk_total = 0
        self.temp = 0
        self.fan_pct = 0
        self.net_if = "init"
        self.ssid = "Searching..."
        self.ip = "..."
        self.mac = "..."
        self.net_speed = "0 KB/s"
        self.services = {}
        
        self.last_net_io = psutil.net_io_counters()
        self.last_time = time.time()
        # 【新增】记录上次检查服务的时间
        self.last_service_check_time = 0

data = SystemData()

# --- 5. 辅助功能 ---

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
    except:
        return None

def get_service_status(service_name, is_user=False):
    try:
        # 如果是用户级服务，需要加上 --user 参数
        cmd = ["systemctl", "--user", "is-active", service_name] if is_user else ["systemctl", "is-active", service_name]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
        return output == "active"
    except subprocess.CalledProcessError:
        # 如果服务未运行，systemctl 会返回非零状态码导致报错，这里直接返回 False
        return False
    except:
        return False

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except:
        return 0.0

def get_fan_speed():
    try:
        cur_path = "/sys/class/thermal/cooling_device0/cur_state"
        max_path = "/sys/class/thermal/cooling_device0/max_state"
        if os.path.exists(cur_path):
            with open(cur_path, "r") as f:
                cur_val = int(f.read())
            max_val = 255
            if os.path.exists(max_path):
                with open(max_path, "r") as f:
                    val = int(f.read())
                    if val > 0: max_val = val
            return int((cur_val / max_val) * 100)
    except:
        pass
    return 0

def get_ssid(interface):
    if interface.startswith("wlan"):
        ssid = run_cmd(f"iwgetid -r {interface}")
        if ssid: return ssid
        return "Disconnected"
    return "Wired"

def update_system_data():
    global data
    data.cpu_pct = psutil.cpu_percent()
    
    vm = psutil.virtual_memory()
    data.ram_pct = vm.percent
    data.ram_used = vm.used
    data.ram_total = vm.total
    
    du = psutil.disk_usage('/')
    data.disk_pct = du.percent
    data.disk_used = du.used
    data.disk_total = du.total
    
    data.temp = get_cpu_temp()
    data.fan_pct = get_fan_speed()
    
    addrs = psutil.net_if_addrs()
    target_if = None
    if 'wlan0' in addrs:
        for addr in addrs['wlan0']:
            if addr.family == socket.AF_INET: target_if = 'wlan0'
    if not target_if and 'eth0' in addrs:
        for addr in addrs['eth0']:
            if addr.family == socket.AF_INET: target_if = 'eth0'
            
    if target_if: data.net_if = target_if
    elif 'wlan0' in addrs: data.net_if = 'wlan0'
    else: data.net_if = "eth0"
    
    data.ip = "No IP"
    data.mac = "Unknown"
    if data.net_if in addrs:
        for addr in addrs[data.net_if]:
            if addr.family == socket.AF_INET: data.ip = addr.address
            elif addr.family == psutil.AF_LINK: data.mac = addr.address

    data.ssid = get_ssid(data.net_if)

    cur_time = time.time()
    cur_net_io = psutil.net_io_counters()
    time_delta = cur_time - data.last_time
    if time_delta > 0:
        diff = (cur_net_io.bytes_sent + cur_net_io.bytes_recv) - (data.last_net_io.bytes_sent + data.last_net_io.bytes_recv)
        speed_bps = diff / time_delta
        if speed_bps < 1024: data.net_speed = f"{speed_bps:.0f} B/s"
        elif speed_bps < 1024**2: data.net_speed = f"{speed_bps/1024:.1f} KB/s"
        else: data.net_speed = f"{speed_bps/1024/1024:.1f} MB/s"
    
    data.last_net_io = cur_net_io
    data.last_time = cur_time
    
    # === 低频数据 (服务检查) - 每隔 SERVICE_CHECK_INTERVAL 秒更新一次 ===
    if cur_time - data.last_service_check_time > SERVICE_CHECK_INTERVAL:
        for svc in MONITORED_SERVICES:
            is_user_svc = svc.get("is_user", False)
            data.services[svc['name']] = get_service_status(svc['service'], is_user=is_user_svc)
        
        # 更新时间戳
        data.last_service_check_time = cur_time

# --- 6. 绘图函数 ---

def draw_panel(surface, x, y, w, h, title):
    pygame.draw.rect(surface, COLOR_PANEL_BG, (x, y, w, h), border_radius=5)
    pygame.draw.rect(surface, COLOR_BORDER, (x, y, w, h), 1, border_radius=5)
    pygame.draw.rect(surface, COLOR_BORDER, (x, y, w, 22), border_top_left_radius=5, border_top_right_radius=5)
    surface.blit(font_label.render(title, True, COLOR_TEXT_LABEL), (x + 8, y + 4))

# 【修改】：color 参数默认为 None，内部获取当前全局变量
def draw_progress_bar(surface, x, y, w, h, percent, color=None):
    if color is None: color = COLOR_ACCENT
    # 亮色模式下，进度条底色要深一点才看得见
    bg_bar_color = (200, 200, 200) if is_light_theme else (30, 30, 45)
    
    pygame.draw.rect(surface, bg_bar_color, (x, y, w, h), border_radius=2)
    fill_w = int(w * (percent / 100))
    if fill_w > 0:
        pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=2)

def get_color(percent):
    if percent < 70: return COLOR_ACCENT
    if percent < 90: return COLOR_WARN
    return COLOR_DANGER

scroll_offset = 0
def draw_scrolling_text(surface, text, x, y, max_w, font, color):
    # 动态计算垂直居中需要行高
    text_surf = font.render(text, True, color)
    text_w = text_surf.get_width()
    
    if text_w <= max_w:
        surface.blit(text_surf, (x, y - text_surf.get_height() // 2))
    else:
        clip_rect = pygame.Rect(x, y - 10, max_w, 20)
        original_clip = surface.get_clip()
        surface.set_clip(clip_rect)
        gap = 40
        total_cycle_w = text_w + gap
        current_x = x - (scroll_offset % total_cycle_w)
        
        draw_y = y - text_surf.get_height() // 2
        surface.blit(text_surf, (current_x, draw_y))
        surface.blit(text_surf, (current_x + total_cycle_w, draw_y))
        surface.set_clip(original_clip)

# --- 7. 主循环 ---

running = True
last_update_ts = 0

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: running = False

    # --- 颜色反转逻辑 (每隔1小时) ---
    current_ts = time.time()
    if current_ts - last_theme_switch_time > THEME_SWITCH_INTERVAL:
        is_light_theme = not is_light_theme # 切换开关
        set_theme(is_light_theme)           # 应用主题
        last_theme_switch_time = current_ts # 重置计时
        # print(f"Theme switched! Light mode: {is_light_theme}") # 调试用

    if current_ts - last_update_ts > DATA_UPDATE_INTERVAL:
        update_system_data()
        last_update_ts = current_ts

    scroll_offset += 1 

    screen.fill(COLOR_BG)
    
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d %a")
    time_str = now.strftime("%H:%M:%S")

    # 顶部栏
    pygame.draw.rect(screen, COLOR_PANEL_BG, (0, 0, SCREEN_WIDTH, 35))
    pygame.draw.line(screen, COLOR_ACCENT, (0, 34), (SCREEN_WIDTH, 34), 2)
    screen.blit(font_date.render(date_str, True, COLOR_TEXT_LABEL), (10, 6))
    screen.blit(font_header.render(time_str, True, COLOR_ACCENT), (SCREEN_WIDTH - 120, 4))

    panel_y = 40; panel_h = 200; panel_w = 225
    
    # --- HARDWARE ---
    draw_panel(screen, 10, panel_y, panel_w, panel_h, "HARDWARE")
    start_x = 20; start_y = panel_y + 32; gap_y = 32
    
    def draw_hw(idx, label, val_text, pct, col, alt_text=None):
        row_y = start_y + idx * gap_y
        center_y = row_y + gap_y // 2
        
        # 1. Label
        s_label = font_label.render(label, True, COLOR_TEXT_LABEL)
        screen.blit(s_label, (start_x, center_y - s_label.get_height() // 2))
        
        # 2. Value
        s_val = font_val.render(val_text, True, COLOR_TEXT_VAL)
        screen.blit(s_val, (start_x + 45, center_y - s_val.get_height() // 2))
        
        # 3. Progress or Text
        if alt_text:
            s_alt = font_val.render(alt_text, True, COLOR_ACCENT)
            screen.blit(s_alt, (start_x + 110, center_y - s_alt.get_height() // 2))
        else:
            draw_progress_bar(screen, start_x + 110, center_y - 4, 80, 8, pct, col)

    draw_hw(0, "CPU", f"{data.cpu_pct}%", data.cpu_pct, get_color(data.cpu_pct))
    
    ram_usage_str = f"{data.ram_used/1024**3:.1f}/{data.ram_total/1024**3:.1f}G"
    draw_hw(1, "RAM", f"{data.ram_pct}%", 0, COLOR_ACCENT, alt_text=ram_usage_str)
    
    disk_usage_str = f"{data.disk_used/1024**3:.1f}/{data.disk_total/1024**3:.1f}G"
    draw_hw(2, "DISK", f"{data.disk_pct}%", 0, COLOR_ACCENT, alt_text=disk_usage_str)
    
    t_col = get_color((data.temp - 40) * 2)
    draw_hw(3, "TEMP", f"{data.temp:.0f}°C", min(data.temp, 100), t_col)
    
    draw_hw(4, "FAN", f"{data.fan_pct}%", data.fan_pct, COLOR_ACCENT)

    # --- NETWORK ---
    draw_panel(screen, 245, panel_y, panel_w, panel_h, "NETWORK")
    label_x = 255; val_x = 300; net_start_y = panel_y + 32; net_gap = 32
    
    # 【修改】：color 参数默认为 None
    def draw_net(idx, label, value, color=None, scroll=False):
        if color is None: color = COLOR_ACCENT
        row_y = net_start_y + idx * net_gap
        center_y = row_y + net_gap // 2
        
        s_label = font_label.render(label, True, COLOR_TEXT_LABEL)
        screen.blit(s_label, (label_x, center_y - s_label.get_height() // 2))
        
        if scroll:
            draw_scrolling_text(screen, value, val_x, center_y, 150, font_val, color)
        else:
            s_val = font_val.render(value, True, color)
            screen.blit(s_val, (val_x, center_y - s_val.get_height() // 2))

    draw_net(0, "IFACE", data.net_if, COLOR_TEXT_VAL)
    draw_net(1, "SSID", data.ssid, COLOR_TEXT_VAL, scroll=True)
    draw_net(2, "IP", data.ip, COLOR_ACCENT)
    draw_net(3, "MAC", data.mac.upper(), COLOR_ACCENT)
    draw_net(4, "NET", data.net_speed, COLOR_WARN)

    # --- SERVICES ---
    svc_y = 245; svc_h = 70
    draw_panel(screen, 10, svc_y, 460, svc_h, "SERVICES")
    
    svc_count = len(MONITORED_SERVICES)
    if svc_count > 0:
        slot_width = 460 / svc_count
        for i, svc in enumerate(MONITORED_SERVICES):
            name = svc['name']
            is_active = data.services.get(name, False)
            center_x = 10 + (i * slot_width) + (slot_width / 2)
            cur_y = svc_y + 22 + (svc_h - 22) // 2
            
            text_surf = font_mini.render(name, True, COLOR_TEXT_VAL)
            total_content_w = 12 + 5 + text_surf.get_width()
            start_content_x = center_x - (total_content_w / 2)
            
            status_color = COLOR_OK if is_active else COLOR_DANGER
            pygame.draw.circle(screen, status_color, (start_content_x + 6, cur_y), 6)
            screen.blit(text_surf, (start_content_x + 18, cur_y - text_surf.get_height() // 2))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
