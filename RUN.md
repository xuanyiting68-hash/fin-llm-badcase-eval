# 运行采集（Windows PowerShell）

```powershell
# 1. 克隆仓库并安装依赖（只需一次）
git clone https://github.com/xuanyiting68-hash/fin-llm-badcase-eval.git
cd fin-llm-badcase-eval
pip install -r requirements.txt

# 2. 复制 .env.example 为 .env，用记事本填入四个 Key
Copy-Item .env.example .env
notepad .env

# 3. 检查配置（不发请求）
python scripts/collect.py --dry-run

# 4. 每家先试 1 道题
python scripts/collect.py --ids A01

# 5. 打开 responses\ 下的文件确认正常后，跑全部题目
python scripts/collect.py
```

- 中途断了直接重跑第 5 步，已采集的题会自动跳过。
- 要重采某道题：`python scripts/collect.py --models kimi --ids G01 --force`
- Kimi 账户限速较低，脚本每 21 秒发一次请求，30 题约 10–20 分钟（思考模式回答较慢）。
- 采集日志在 `responses\collect_log.csv`。
