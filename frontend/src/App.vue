<script setup lang="ts">
// App.vue 只放 el-config-provider(zhCn) + router-view，不写业务（规范 §3）
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>
