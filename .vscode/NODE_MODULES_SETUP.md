# 前端 Node.js 依赖构建指南

本文档说明如何为前端项目安装和配置 `node_modules` 依赖。

---

## 📋 前置要求

- **Node.js 18+** 已安装
- **npm** 或 **yarn** 或 **pnpm** 包管理器
- 确认 Node.js 版本：
  ```bash
  node --version
  # 应该 >= 18.0.0
  
  npm --version
  # 或
  yarn --version
  # 或
  pnpm --version
  ```

---

## 🚀 快速开始

### 使用 npm（推荐）

```bash
# 1. 在项目根目录
cd D:\code\cursor\demo\secmanus

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

### 使用 yarn

```bash
# 1. 在项目根目录
cd D:\code\cursor\demo\secmanus

# 2. 安装依赖
yarn install

# 3. 启动开发服务器
yarn dev
```

### 使用 pnpm

```bash
# 1. 在项目根目录
cd D:\code\cursor\demo\secmanus

# 2. 安装依赖
pnpm install

# 3. 启动开发服务器
pnpm dev
```

---

## 📝 详细步骤

### 步骤 1: 检查 Node.js 环境

```bash
# 检查 Node.js 版本
node --version
# 应该显示 v18.x.x 或更高版本

# 检查 npm 版本
npm --version
# 应该显示 9.x.x 或更高版本

# 如果 Node.js 未安装或版本过低，请先安装/升级 Node.js
# Windows: 从 https://nodejs.org/ 下载安装
# Mac: brew install node
# Linux: 使用 nvm 或包管理器安装
```

### 步骤 2: 清理旧的依赖（可选）

如果之前安装过依赖但出现问题，可以先清理：

```bash
# 删除 node_modules 目录
# Windows
rmdir /s node_modules

# Linux/Mac
rm -rf node_modules

# 删除锁文件（可选，如果遇到依赖冲突）
# npm
del package-lock.json  # Windows
rm package-lock.json   # Linux/Mac

# yarn
del yarn.lock
rm yarn.lock

# pnpm
del pnpm-lock.yaml
rm pnpm-lock.yaml
```

### 步骤 3: 安装依赖

#### 使用 npm（项目默认）

```bash
# 标准安装
npm install

# 如果安装速度慢，可以使用国内镜像源
npm install --registry=https://registry.npmmirror.com

# 或设置镜像源（永久）
npm config set registry https://registry.npmmirror.com

# 验证安装
npm list --depth=0
```

#### 使用 yarn

```bash
# 安装依赖
yarn install

# 如果安装速度慢，可以使用国内镜像源
yarn install --registry https://registry.npmmirror.com

# 或设置镜像源（永久）
yarn config set registry https://registry.npmmirror.com
```

#### 使用 pnpm

```bash
# 安装依赖
pnpm install

# 如果安装速度慢，可以使用国内镜像源
pnpm install --registry https://registry.npmmirror.com

# 或设置镜像源（永久）
pnpm config set registry https://registry.npmmirror.com
```

### 步骤 4: 验证安装

```bash
# 检查 node_modules 目录是否存在
# Windows
dir node_modules

# Linux/Mac
ls -la node_modules

# 检查关键依赖是否安装
npm list react
npm list vite
npm list typescript

# 或使用 yarn
yarn list --pattern react
yarn list --pattern vite

# 或使用 pnpm
pnpm list react
pnpm list vite
```

### 步骤 5: 配置环境变量（如果需要）

1. **复制环境变量模板**：
   ```bash
   # Windows
   copy env.local.template .env.local
   
   # Linux/Mac
   cp env.local.template .env.local
   ```

2. **编辑 `.env.local` 文件**，填入必要的配置：
   - `VITE_SUPABASE_URL` - Supabase 项目 URL
   - `VITE_SUPABASE_PUBLISHABLE_KEY` - Supabase 公钥
   - `VITE_API_MODE` - API 模式（`local` 或 `supabase`）
   - 其他环境变量（详见 `env.local.template`）

### 步骤 6: 启动开发服务器

```bash
# 使用 npm
npm run dev

# 使用 yarn
yarn dev

# 使用 pnpm
pnpm dev
```

**成功启动的标志**：
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:8080/
  ➜  Network: use --host to expose
```

访问 `http://localhost:8080` 应该能看到应用界面。

### 步骤 7: 构建生产版本（可选）

```bash
# 构建生产版本
npm run build

# 构建开发版本
npm run build:dev

# 预览构建结果
npm run preview
```

构建产物会输出到 `dist/` 目录。

---

## 🔧 常见问题

### Q1: `npm install` 失败或速度很慢？

**解决方案**：

```bash
# 1. 使用国内镜像源
npm install --registry=https://registry.npmmirror.com

# 2. 永久设置镜像源
npm config set registry https://registry.npmmirror.com

# 3. 清除 npm 缓存
npm cache clean --force

# 4. 删除 node_modules 和 package-lock.json 后重新安装
rm -rf node_modules package-lock.json
npm install
```

**其他镜像源**：
- 淘宝镜像：`https://registry.npmmirror.com`
- 腾讯云镜像：`https://mirrors.cloud.tencent.com/npm/`
- 华为云镜像：`https://repo.huaweicloud.com/repository/npm/`

### Q2: 依赖版本冲突？

**解决方案**：

```bash
# 1. 删除 node_modules 和锁文件
rm -rf node_modules package-lock.json

# 2. 清理 npm 缓存
npm cache clean --force

# 3. 重新安装
npm install

# 4. 如果仍有问题，尝试更新依赖
npm update

# 5. 或使用 --legacy-peer-deps 标志
npm install --legacy-peer-deps
```

### Q3: `node_modules` 目录太大？

**这是正常的**：
- `node_modules` 目录通常很大（几百 MB 到几 GB）
- 包含所有依赖及其子依赖
- 已在 `.gitignore` 中，不会提交到 Git

**优化建议**：
```bash
# 使用 pnpm（更节省空间）
npm install -g pnpm
pnpm install

# 或使用 yarn（PnP 模式，但需要额外配置）
yarn install --pnp
```

### Q4: 权限错误（EACCES）？

**Windows**：
- 以管理员身份运行 PowerShell 或 CMD

**Linux/Mac**：
```bash
# 不要使用 sudo 安装全局包
# 配置 npm 使用其他目录
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
export PATH=~/.npm-global/bin:$PATH

# 或修复现有目录权限
sudo chown -R $(whoami) ~/.npm
sudo chown -R $(whoami) /usr/local/lib/node_modules
```

### Q5: 端口 8080 被占用？

**解决方案**：

```bash
# Windows: 查找占用端口的进程
netstat -ano | findstr :8080

# Linux/Mac: 查找占用端口的进程
lsof -i :8080

# 终止进程或修改 Vite 配置使用其他端口
# 在 vite.config.ts 中：
# export default defineConfig({
#   server: {
#     port: 3000  // 使用其他端口
#   }
# })
```

### Q6: TypeScript 类型错误？

**解决方案**：

```bash
# 1. 确保安装了 TypeScript
npm install --save-dev typescript

# 2. 检查 tsconfig.json 配置
# 3. 重启 VS Code/Cursor
# 4. 运行类型检查
npm run lint

# 5. 如果使用 Vite，确保安装了 @vitejs/plugin-react
```

### Q7: 构建失败？

**检查**：

```bash
# 1. 检查 Node.js 版本（需要 >= 18）
node --version

# 2. 检查依赖是否完整安装
npm list --depth=0

# 3. 查看详细错误信息
npm run build -- --debug

# 4. 清理后重新构建
rm -rf node_modules dist
npm install
npm run build
```

### Q8: 如何切换包管理器？

**从 npm 切换到 yarn**：
```bash
# 删除 npm 锁文件
rm package-lock.json

# 安装 yarn（如果未安装）
npm install -g yarn

# 使用 yarn 安装
yarn install
```

**从 npm 切换到 pnpm**：
```bash
# 删除 npm 锁文件
rm package-lock.json

# 安装 pnpm（如果未安装）
npm install -g pnpm

# 使用 pnpm 安装
pnpm install
```

**注意**：项目使用 `package-lock.json`（npm），建议统一使用 npm。

---

## 📂 项目依赖说明

### 主要依赖（dependencies）

- **React 18.3.1** - UI 框架
- **React Router 6.30.1** - 路由管理
- **Vite 5.4.19** - 构建工具和开发服务器
- **TypeScript 5.8.3** - 类型系统
- **Tailwind CSS 3.4.17** - CSS 框架
- **Radix UI** - 无样式 UI 组件库
- **@supabase/supabase-js** - Supabase 客户端
- **@tanstack/react-query** - 数据获取和状态管理
- **Zod** - 数据验证
- **React Hook Form** - 表单管理

### 开发依赖（devDependencies）

- **ESLint** - 代码检查
- **TypeScript ESLint** - TypeScript 代码检查
- **PostCSS** - CSS 处理
- **Autoprefixer** - CSS 自动前缀

---

## 📂 node_modules 目录结构

安装成功后，`node_modules` 目录结构应该类似：

```
node_modules/
├── .bin/                    # 可执行文件
│   ├── vite
│   ├── tsc
│   └── eslint
├── react/                   # React 核心库
├── react-dom/               # React DOM
├── vite/                    # Vite 构建工具
├── typescript/              # TypeScript 编译器
├── @radix-ui/               # Radix UI 组件
│   ├── react-accordion/
│   ├── react-dialog/
│   └── ...
├── @supabase/               # Supabase 客户端
├── @tanstack/               # TanStack 库
├── tailwindcss/             # Tailwind CSS
└── ...                      # 其他依赖
```

**目录大小**：通常 200MB - 1GB，取决于安装的依赖数量。

---

## ⚠️ 重要注意事项

### 1. 不要提交 node_modules 到 Git

- `node_modules/` 目录已在 `.gitignore` 中
- 每个开发者需要自己安装依赖
- 只提交 `package.json` 和 `package-lock.json` 文件

### 2. 使用 package-lock.json

- 项目使用 `package-lock.json` 锁定依赖版本
- **不要删除** `package-lock.json`（除非遇到严重冲突）
- 提交 `package-lock.json` 到 Git，确保团队使用相同版本

### 3. 依赖是项目特定的

- 不要在不同项目间共享 `node_modules`
- 每个项目应该有独立的依赖安装
- 依赖安装在项目根目录的 `node_modules/`

### 4. 定期更新依赖

```bash
# 检查过时的包
npm outdated

# 更新所有包到最新版本（谨慎使用）
npm update

# 更新特定包
npm install package-name@latest

# 更新到最新主版本（可能包含破坏性更改）
npm install package-name@latest --save
```

### 5. 使用镜像源加速（可选）

**临时使用**：
```bash
npm install --registry=https://registry.npmmirror.com
```

**永久设置**：
```bash
npm config set registry https://registry.npmmirror.com

# 验证设置
npm config get registry
```

**恢复官方源**：
```bash
npm config set registry https://registry.npmjs.org/
```

---

## 🧪 验证清单

完成依赖安装后，请验证以下项目：

- [ ] Node.js 版本 >= 18.0.0
- [ ] npm 版本 >= 9.0.0
- [ ] `node_modules` 目录已创建
- [ ] 所有依赖已安装（`npm list --depth=0` 无错误）
- [ ] `.env.local` 文件已创建并配置（如果需要）
- [ ] 可以成功启动开发服务器（`npm run dev`）
- [ ] 浏览器可以访问 `http://localhost:8080`
- [ ] 可以成功构建生产版本（`npm run build`）

---

## 📚 相关文档

- [Node.js 官方文档](https://nodejs.org/)
- [npm 官方文档](https://docs.npmjs.com/)
- [Vite 官方文档](https://vitejs.dev/)
- [React 官方文档](https://react.dev/)
- [TypeScript 官方文档](https://www.typescriptlang.org/)
- 项目 `package.json` 文件
- `.vscode/README.md` - VS Code 配置说明

---

## 💡 提示

- 如果遇到问题，先检查 Node.js 版本和网络连接
- 使用 `npm list` 查看已安装的包
- 使用 `npm outdated` 检查过时的包
- 查看终端错误信息，通常会有明确的提示
- 确保网络连接正常（安装依赖需要下载包）
- 如果安装失败，尝试清除缓存：`npm cache clean --force`
- 大型项目安装可能需要几分钟，请耐心等待

---

## 🔄 常用命令参考

```bash
# 安装依赖
npm install

# 安装特定包
npm install package-name

# 安装开发依赖
npm install --save-dev package-name

# 卸载包
npm uninstall package-name

# 更新包
npm update package-name

# 查看已安装的包
npm list

# 查看过时的包
npm outdated

# 运行脚本
npm run dev          # 启动开发服务器
npm run build        # 构建生产版本
npm run lint         # 代码检查
npm run preview      # 预览构建结果

# 清理
npm cache clean --force  # 清除 npm 缓存
```

---

## 🌐 国内镜像源配置

### npm 镜像源

```bash
# 设置淘宝镜像
npm config set registry https://registry.npmmirror.com

# 设置腾讯云镜像
npm config set registry https://mirrors.cloud.tencent.com/npm/

# 恢复官方源
npm config set registry https://registry.npmjs.org/

# 查看当前镜像源
npm config get registry
```

### yarn 镜像源

```bash
# 设置淘宝镜像
yarn config set registry https://registry.npmmirror.com

# 恢复官方源
yarn config set registry https://registry.yarnpkg.com
```

### pnpm 镜像源

```bash
# 设置淘宝镜像
pnpm config set registry https://registry.npmmirror.com

# 恢复官方源
pnpm config set registry https://registry.npmjs.org/
```

