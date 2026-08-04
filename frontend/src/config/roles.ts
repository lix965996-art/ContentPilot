import type { RoleCode } from '@/types/user'

/** Single source of truth for role scope copy (UI + docs). */
export const ROLE_SCOPES: Record<
  RoleCode,
  { label: string; summary: string; canManageSystem: boolean; canManageBusiness: boolean }
> = {
  ADMIN: {
    label: '系统管理员',
    summary: '只管理系统：平台账号、用户、大模型与全局配置；不参与内容运营。',
    canManageSystem: true,
    canManageBusiness: false,
  },
  OPERATOR: {
    label: '内容运营者',
    summary: '负责内容生产、排期发布、数据导入与对比验证；不能改系统设置和平台授权。',
    canManageSystem: false,
    canManageBusiness: true,
  },
  VIEWER: {
    label: '查看者',
    summary: '只读浏览内容、排期、数据与分析结果；不能创建、修改或导入任何业务数据。',
    canManageSystem: false,
    canManageBusiness: false,
  },
}

export function pickPrimaryRole(codes: RoleCode[]): RoleCode | null {
  if (codes.includes('ADMIN')) return 'ADMIN'
  if (codes.includes('OPERATOR')) return 'OPERATOR'
  if (codes.includes('VIEWER')) return 'VIEWER'
  return codes[0] ?? null
}

export function canManageSystem(codes: RoleCode[]): boolean {
  return codes.includes('ADMIN')
}

export function canManageBusiness(codes: RoleCode[]): boolean {
  return codes.includes('OPERATOR')
}

export function isSystemAdminOnly(codes: RoleCode[]): boolean {
  return codes.includes('ADMIN') && !codes.includes('OPERATOR')
}

export function isViewerOnly(codes: RoleCode[]): boolean {
  return codes.includes('VIEWER') && !canManageBusiness(codes)
}
