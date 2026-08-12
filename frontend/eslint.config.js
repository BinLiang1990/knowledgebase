import antfu from '@antfu/eslint-config'

export default antfu({
  vue: true,
  typescript: true,
  // 使用 ESLint 自带格式化能力，不引 prettier，避免规则打架（前端开发规范 §2.2）
  stylistic: { indent: 2, quotes: 'single', semi: false },
  // markdown 忽略：运维.md 等文档里的片段代码块不是可解析的完整源码
  ignores: ['dist', 'node_modules', 'auto-imports.d.ts', 'components.d.ts', 'public', '**/*.md'],
})
