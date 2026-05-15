<div align="center">

# 🎁 营销与数据平台产品部 奖品管理

**部门内部奖品申请与库存管理系统**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Vercel](https://img.shields.io/badge/Vercel-Deployed-000000?logo=vercel&logoColor=white)](https://vercel.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## 功能概览

<table>
<tr>
<td width="50%">

### 📦 奖品管理（管理员）
- 添加、编辑、删除奖品
- 支持分类：实物奖品、e卡、优惠券、虚拟权益、其他
- 库存管理与低库存预警
- 奖品图片上传

</td>
<td width="50%">

### 📝 奖品申请
- 填写申请人、用途，勾选奖品并填写数量
- 支持拖拽/点击上传活动现场照片
- 提交后自动扣减库存
- 完成后跳转至申请记录列表

</td>
</tr>
<tr>
<td>

### 📋 申请记录
- **普通用户**：查看自己提交的申请
- **管理员**：查看全部记录，支持搜索和状态筛选
- 查看详情（只读）/ 编辑修改
- 管理员可关单，关单后不可再修改
- 取消申请自动恢复库存

</td>
<td>

### 📊 数据导出（管理员）
- 一键导出全部申请记录为 Excel 文件
- 包含编号、申请人、用途、奖品、数量、状态、时间等字段

</td>
</tr>
</table>

## 在线体验

> 🔗 [点击访问](https://prize-manager.vercel.app/)

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
# 1. 克隆项目
git clone https://github.com/Rosa-zhurong/prize-manager.git
cd prize-manager

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动开发服务器
python app.py
```

打开浏览器访问 **http://localhost:5000**

### 部署到 Vercel

**第一步：准备数据库**

1. 在 [Supabase](https://supabase.com) 创建项目
2. 进入 `Settings` → `Database` → `Connection string`
3. 选择 **Transaction pooler**（端口 `6543`），复制连接串

> 连接串格式：`postgresql://postgres.xxxx:密码@aws-0-区域.pooler.supabase.com:6543/postgres`

**第二步：部署**

1. Fork 本仓库到你的 GitHub
2. 在 [Vercel](https://vercel.com) 导入该项目
3. 添加环境变量 `DATABASE_URL`，值为上面复制的连接串
4. 点击 Deploy，等待部署完成

> ⚠️ Vercel 的 `DATABASE_URL` 可能以 `postgres://` 开头，代码会自动转换为 `postgresql://`，无需手动处理。

## 项目结构

```
prize-manager/
├── app.py                # Flask 应用主文件（路由、模型、业务逻辑）
├── api/index.py          # Vercel Serverless 入口
├── requirements.txt      # Python 依赖
├── vercel.json           # Vercel 部署配置
├── templates/            # Jinja2 模板
│   ├── base.html         # 基础布局（导航、Toast 提示、图片灯箱）
│   ├── index.html        # 首页（奖品平铺/列表展示）
│   ├── apply.html        # 申请表单（勾选奖品、上传照片）
│   ├── apply_detail.html # 申请详情（查看/编辑模式）
│   ├── history.html      # 申请记录列表
│   ├── prizes.html       # 奖品管理列表（管理员）
│   └── prize_form.html   # 奖品添加/编辑表单（管理员）
├── static/               # 静态资源（CSS、JS、图片）
└── uploads/              # 用户上传的活动照片
```

## 管理员模式

导航栏右侧点击 **「切换管理员」**，输入密码即可进入管理员模式。

管理员专属功能：
- 管理奖品（增删改）
- 查看全部申请记录
- 关闭申请单（关单后申请人不可修改）
- 导出申请记录为 Excel

> 默认管理员密码：`1234567890`
> 
> 🔐 **请在生产环境中修改 `app.py` 中的 `ADMIN_PASSWORD`**

## License

[MIT](LICENSE)
