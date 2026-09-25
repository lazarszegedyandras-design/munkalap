export const MODULES = {
  service: { label: 'Szerviz', route: '/service' },
  hr: { label: 'HR', route: '/hr' },
  crm: { label: 'CRM', route: '/crm' },
  procurement: { label: 'Beszerzés', route: '/procurement' },
  admin: { label: 'Admin', route: '/admin' },
}

export function hasModule(user, moduleCode) {
  return Boolean(user?.modules?.includes(moduleCode))
}

export function hasPermission(user, permissionCode) {
  return user?.role?.name === 'Admin' || Boolean(user?.permissions?.includes(permissionCode))
}

export function moduleLabel(moduleCode) {
  return MODULES[moduleCode]?.label || moduleCode
}
