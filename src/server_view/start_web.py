"""
Yosuga Server Web UI 启动脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app import run_server

if __name__ == '__main__':
    run_server(host="0.0.0.0", port=8089, debug=False)