<div align="center">

# 营销与数据平台产品部 奖品管理

**部门内部奖品申请与库存管理系统**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Vercel](https://img.shields.io/badge/Vercel-Deployed-000000?logo=vercel&logoColor=white)](https://vercel.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

在线体验：https://prize-manager.vercel.app

</div>

---

## 功能特性

| 角色 | 功能 |
|------|------|
| **普通用户** | 申请奖品、查看/编辑自己的申请、查看申请记录 |
| **管理员** | 奖品管理（增删改）、查看全部申请记录、完结申请、导出 Excel |

### 奖品申请

- 勾选奖品并填写数量，支持多件
- 拖拽或点击上传活动现场照片
- 提交后自动扣减库存
- 申请记录直接展示在申请页面，支持继续新建申请

### 申请管理

- 普通用户可查看、编辑自己的申请
- 管理员可查看全部记录，支持按状态筛选和关键词搜索
- 管理员可「完结」申请，完结后申请人不可再修改
- 取消申请自动恢复库存

### 数据导出

- 管理员一键导出全部申请记录为 Excel
- 包含编号、申请人、用途、奖品、数量、状态、时间等字段

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python Flask + SQLAlchemy |
| 数据库 | PostgreSQL（Supabase）/ SQLite（本地开发） |
| 前端 | Bootstrap 5.3 + Bootstrap Icons |
| 部署 | Vercel Serverless |

## 快速开始

### 本地开发

```bash
# 克隆项目
git clone https://github.com/Rosa-zhurong/prize-manager.git
cd prize-manager

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python app.py
```

打开浏览器访问 http://localhost:5000

### 部署到 Vercel

**1. 准备数据库**

在 [Supabase](https://supabase.com) 创建项目，进入 Settings → Database → Connection string，选择 **Transaction pooler**（端口 `6543`），复制连接串。

**2. 部署**

1. Fork 本仓库
2. 在 [Vercel](https://vercel.com) 导入项目
3. 添加环境变量 `DATABASE_URL`，值为 Supabase 连接串
4. 点击 Deploy

> Vercel 的 `DATABASE_URL` 可能以 `postgres://` 开头，代码会自动转换为 `postgresql://`，无需手动处理。

## 项目结构

```
prize-manager/
├── app.py                # Flask 应用（路由、模型、业务逻辑）
├── api/index.py          # Vercel Serverless 入口
├── requirements.txt      # Python 依赖
├── vercel.json           # Vercel 部署配置
├── templates/            # Jinja2 模板
│   ├── base.html         # 基础布局（导航、Toast、图片灯箱）
│   ├── index.html        # 首页（奖品展示）
│   ├── apply.html        # 申请表单 + 申请记录
│   ├── apply_detail.html # 申请详情（查看/编辑）
│   ├── history.html      # 全部申请记录（管理员）
│   ├── prizes.html       # 奖品管理（管理员）
│   └── prize_form.html   # 奖品添加/编辑（管理员）
└── uploads/              # 用户上传的活动照片
```

## 管理员模式

导航栏右侧点击「切换管理员」，输入密码进入管理员模式。

默认密码：`1234567890`

> 请在生产环境中修改 `app.py` 中的 `ADMIN_PASSWORD`

## License

[MIT](LICENSE)
