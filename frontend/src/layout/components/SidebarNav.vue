<script setup lang="ts">
import type { Component } from 'vue'
import { Clock, Grid, SetUp } from '@element-plus/icons-vue'
import logoUrl from '@/assets/logo.png'
import { asyncRoutes } from '@/router/asyncRoutes'

// meta.icon 存 Element Plus 图标名字符串（规范 §5.6），这里做一次名称 → 组件
// 映射；新增菜单项时在此登记图标即可。
const ICONS: Record<string, Component> = { Grid, SetUp, Clock }

// 菜单直接从路由模块推导（hidden 的子页不进菜单），新增模块零改动
const menuItems = asyncRoutes
  .filter(r => r.meta?.title && !r.meta.hidden)
  .sort((a, b) => (a.meta?.order ?? 99) - (b.meta?.order ?? 99))
</script>

<template>
  <aside class="side">
    <div class="side-logo">
      <img :src="logoUrl" alt="" class="side-logo-mark">
      <span class="name">
        知识库管理
        <small>KNOWLEDGE BASE ADMIN</small>
      </span>
    </div>
    <div class="side-group">
      全局
    </div>
    <nav class="side-menu">
      <RouterLink
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        class="side-item"
        active-class="sel"
      >
        <span class="ic">
          <el-icon v-if="item.meta?.icon && ICONS[item.meta.icon]">
            <component :is="ICONS[item.meta.icon]" />
          </el-icon>
        </span>
        {{ item.meta!.title }}
      </RouterLink>
    </nav>
    <div class="side-foot">
      v0.1 · Vue 3 + 真实后端
      <br>
      接口约定见 docs/PRD.md §4.10
    </div>
  </aside>
</template>
