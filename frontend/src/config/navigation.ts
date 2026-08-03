import type { Component } from 'vue'
import {
  Activity,
  BarChart3,
  Beaker,
  CalendarDays,
  Clock3,
  FileText,
  Flame,
  Image,
  LayoutDashboard,
  PenLine,
  Rocket,
  Settings,
  Share2,
} from 'lucide-vue-next'
import type { RoleCode } from '@/types/user'

export interface NavItem {
  label: string
  /** Vue Router route name */
  name: string
  icon: Component
  roles: RoleCode[]
  /** Sidebar section label; empty string = top-level (no section header) */
  group: string
  /** Whether this item appears in the command-palette search (default true) */
  searchable?: boolean
}

/**
 * Single source of truth for all navigation entries.
 *
 * - AppSidebar renders items grouped by ``group`` with icons.
 * - AppTopbar filters ``searchable !== false`` items for the command palette.
 *
 * To add / remove a page, edit this file only.
 */
export const NAV_ITEMS: NavItem[] = [
  // ── 顶层 ──
  { label: '工作台', name: 'dashboard', icon: LayoutDashboard, roles: ['ADMIN', 'OPERATOR', 'VIEWER'], group: '' },

  // ── 内容 ──
  { label: '内容库', name: 'articles', icon: FileText, roles: ['ADMIN', 'OPERATOR', 'VIEWER'], group: '内容' },
  { label: '创作', name: 'studio', icon: PenLine, roles: ['ADMIN', 'OPERATOR'], group: '内容' },
  { label: '选题研究', name: 'trends', icon: Flame, roles: ['ADMIN', 'OPERATOR'], group: '内容' },
  { label: '媒体', name: 'media', icon: Image, roles: ['ADMIN', 'OPERATOR'], group: '内容' },

  // ── 发布 ──
  { label: '发布时间', name: 'recommendation', icon: Clock3, roles: ['ADMIN', 'OPERATOR'], group: '发布' },
  { label: '日历', name: 'calendar', icon: CalendarDays, roles: ['ADMIN', 'OPERATOR', 'VIEWER'], group: '发布' },
  { label: '发布', name: 'publish', icon: Rocket, roles: ['ADMIN', 'OPERATOR'], group: '发布' },
  { label: '运行中心', name: 'runs', icon: Activity, roles: ['ADMIN', 'OPERATOR'], group: '发布', searchable: false },
  { label: '平台账号', name: 'platform-accounts', icon: Share2, roles: ['ADMIN', 'OPERATOR'], group: '发布', searchable: false },

  // ── 分析 ──
  { label: '数据', name: 'analytics', icon: BarChart3, roles: ['ADMIN', 'OPERATOR', 'VIEWER'], group: '分析' },
  { label: '实验', name: 'experiments', icon: Beaker, roles: ['ADMIN', 'OPERATOR'], group: '分析' },

  // ── 系统 ──
  { label: '设置', name: 'settings', icon: Settings, roles: ['ADMIN'], group: '系统' },
]

/** Group labels in display order (empty string = ungrouped top-level items). */
export const NAV_GROUPS: string[] = ['', '内容', '发布', '分析', '系统']
