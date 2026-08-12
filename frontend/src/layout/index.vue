<script setup lang="ts">
// 布局壳（UI规范 §2.1：侧栏 228px + 顶栏 64px + 自适应内容区）。
// 页面本体经 router-view 注入 .content。
import SidebarNav from './components/SidebarNav.vue'
import TopBar from './components/TopBar.vue'
</script>

<template>
  <div class="app">
    <SidebarNav />
    <div class="main">
      <TopBar />
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>
