# finance_dw Mac 使用说明

## 结论
这个项目不能把 Windows 的 `.venv` 原样搬到 Mac 用。
正确做法是：迁移源码和数据库，在 Mac 上重建 Python 环境。

## 第一次启动
在 Mac 终端进入项目目录：

```bash
cd finance_dw
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

启动后浏览器会打开本地页面。

## 以后启动
进入项目目录后运行：

```bash
./启动finance_dw-Mac.sh
```

如果提示没有权限，先运行一次：

```bash
chmod +x 启动finance_dw-Mac.sh
```

## 已包含内容
- 项目源码
- 配置文件
- 当前数据库 `data/finance_dw.db`
- 历史备份
- 报表模板和导入样例

## 没包含内容
- Windows 的 `.venv`
- pytest 缓存
- 临时文件
- 运行日志

这些不适合迁到 Mac。
