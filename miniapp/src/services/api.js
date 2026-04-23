import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

// In-memory token — survives localStorage wipes (e.g. from 401 interceptor)
let _memToken = localStorage.getItem('access_token') || null

export function updateApiToken(token) {
  _memToken = token || null
  try {
    if (token) localStorage.setItem('access_token', token)
    else localStorage.removeItem('access_token')
  } catch {}
}

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 65000,
})

api.interceptors.request.use((config) => {
  const token = _memToken || localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      updateApiToken(null)
    }
    return Promise.reject(error)
  }
)

export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),
}

export const storesAPI = {
  list: () => api.get('/stores/'),
  create: (data) => api.post('/stores/', data),
  get: (id) => api.get(`/stores/${id}`),
  update: (id, data) => api.put(`/stores/${id}`, data),
  delete: (id) => api.delete(`/stores/${id}`),
  testCredentials: (data) => api.post('/stores/test-credentials', data),
  createIntegration: (storeId, data) =>
    api.post(`/stores/${storeId}/integrations`, data),
  updateIntegration: (storeId, intId, data) =>
    api.put(`/stores/${storeId}/integrations/${intId}`, data),
  testIntegration: (storeId, intId) =>
    api.post(`/stores/${storeId}/integrations/${intId}/test`),
  syncIntegration: (storeId, intId) =>
    api.post(`/stores/${storeId}/integrations/${intId}/sync`),
  getOnecStock: (storeId, intId, threshold = 5) =>
    api.get(`/stores/${storeId}/integrations/${intId}/stock`, { params: { low_stock_threshold: threshold } }),
  diagnoseIntegration: (storeId, intId) =>
    api.get(`/stores/${storeId}/integrations/${intId}/diagnose`),
  deleteIntegration: (storeId, intId) =>
    api.delete(`/stores/${storeId}/integrations/${intId}`),
  toggleIntegrationStatus: (storeId, intId, status) =>
    api.put(`/stores/${storeId}/integrations/${intId}`, { status }),
}

export const productsAPI = {
  list: (storeId, params) => api.get(`/products/${storeId}`, { params }),
  create: (data) => api.post('/products/', data),
  get: (id) => api.get(`/products/detail/${id}`),
  update: (id, data) => api.put(`/products/detail/${id}`, data),
  delete: (id) => api.delete(`/products/detail/${id}`),
  scanBarcode: (formData) =>
    api.post('/products/scan-barcode', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  recognizePhoto: (formData) =>
    api.post('/products/recognize-photo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  uploadInvoice: (formData) =>
    api.post('/products/upload-invoice', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }),
  saveInvoice: (storeId, products, syncToOnec = false) =>
    api.post(`/products/save-invoice?store_id=${storeId}&sync_to_onec=${syncToOnec}`, products),
  bulkCreate: (storeId, products, syncToOnec = false) =>
    api.post(`/products/bulk-create?store_id=${storeId}&sync_to_onec=${syncToOnec}`, products),
  checkBarcode: (barcode) =>
    api.get('/products/check-barcode', { params: { barcode } }),
  searchGlobal: (q) =>
    api.get('/products/search-global', { params: { q } }),
  quickAdd: (storeId, text, barcode = null) => {
    const fd = new FormData()
    fd.append('store_id', storeId)
    fd.append('text', text)
    if (barcode) fd.append('barcode', barcode)
    return api.post('/products/quick-add', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  parseText: (text) => {
    const fd = new FormData()
    fd.append('text', text)
    return api.post('/products/parse-text', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  syncToOnec: (id) => api.post(`/products/detail/${id}/sync-to-onec`),
  pullFromOnec: (id) => api.post(`/products/detail/${id}/pull-from-1c`),
  bulkDelete: (ids) => api.delete('/products/bulk-delete', { data: { ids } }),
  importCSV: (storeId, file) => {
    const fd = new FormData()
    fd.append('store_id', storeId)
    fd.append('file', file)
    return api.post('/products/import-csv', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
  },
  aiEnrich: (payload) => api.post('/products/ai-enrich', payload, { timeout: 10000 }),
  exportKonturMarket: (storeId, { fmt = 'xlsx', ids = null } = {}) => {
    const params = { store_id: storeId, fmt }
    if (ids && ids.length > 0) params.ids = ids.join(',')
    return api.get('/products/export/kontur-market', { params, responseType: 'blob', timeout: 30000 })
  },
}

export const reportsAPI = {
  summary: (storeId) => api.get(`/reports/${storeId}/summary`),
  lowStock: (storeId, threshold) =>
    api.get(`/reports/${storeId}/low-stock`, { params: { threshold } }),
  activity: (storeId) => api.get(`/reports/${storeId}/activity`),
  inventory: (storeId, category) =>
    api.get(`/reports/${storeId}/inventory`, { params: { category } }),
}

export const adminAPI = {
  stats: () => api.get('/admin/stats'),
  users: (page, limit) => api.get('/admin/users', { params: { page, limit } }),
  getUser: (id) => api.get(`/admin/users/${id}`),
  toggleUser: (id) => api.patch(`/admin/users/${id}/toggle`),
  logs: (level, page) => api.get('/admin/logs', { params: { level, page } }),
  subscriptions: (page, search) => api.get('/admin/subscriptions', { params: { page, search, limit: 20 } }),
  getUserSubscription: (userId) => api.get(`/admin/subscriptions/${userId}`),
  grantSubscription: (userId, days = 30) =>
    api.post(`/admin/subscriptions/${userId}/grant`, { days }),
  revokeSubscription: (userId) => api.delete(`/admin/subscriptions/${userId}`),
  backfillCatalog: () => api.post('/admin/backfill-catalog'),
  importCatalog: (limit, autoClear = false) =>
    api.post('/admin/import-catalog', null, { params: { limit, auto_clear: autoClear }, timeout: 60000 }),
  catalogImportStatus: () => api.get('/admin/catalog-import-status'),
  catalogFileCheck: () => api.get('/admin/catalog-file-check'),
  aiCleanupCatalog: () =>
    api.post('/admin/ai-cleanup-catalog', null, { timeout: 60000 }),
  aiCleanupStatus: () => api.get('/admin/ai-cleanup-status'),
  downloadCatalog: (url, filename) =>
    api.post('/admin/download-catalog', { url, filename }),
  downloadCatalogStatus: () => api.get('/admin/download-catalog-status'),
  products: (params) => api.get('/admin/products', { params }),
  getProduct: (id) => api.get(`/admin/products/${id}`),
  bulkDeleteProducts: (ids) => api.delete('/admin/products/bulk-delete', { data: { ids } }),
  clearCatalog: () => api.delete('/admin/clear-catalog'),
  wipeAll: () => api.delete('/admin/wipe-all'),
  dedupCatalog: () => api.post('/admin/dedup-catalog'),
  getProxyConfig: () => api.get('/admin/proxy-config'),
  setProxyConfig: (proxies) => api.post('/admin/proxy-config', { proxies }),
  testProxy: (proxy_url) => api.post('/admin/test-proxy', { proxy_url }),
  toggleAdmin: (userId) => api.patch(`/admin/users/${userId}/toggle-admin`),
  cleanGarbled: () => api.post('/admin/clean-garbled', null, { timeout: 120000 }),
  globalCatalog: (params) => api.get('/admin/global-catalog', { params }),
}

export const agentAPI = {
  list: (storeId) => api.get('/agent/list', { params: { store_id: storeId } }),
  pair: (storeId, name) => api.post('/agent/pair', { store_id: storeId, name }),
  revoke: (agentId) => api.delete(`/agent/${agentId}`),
  rename: (agentId, name) => api.patch(`/agent/${agentId}`, { name }),
  tasks: (agentId, limit = 50) => api.get(`/agent/${agentId}/tasks`, { params: { limit } }),
  testTask: (agentId, action = 'login_check', payload = {}) =>
    api.post(`/agent/${agentId}/test-task`, { action, payload }),
  info: () => api.get('/agent/info'),
  downloadInstallerExe: (storeId, name = 'Агент') =>
    api.get('/agent/installer.exe', {
      params: { store_id: storeId, name },
      responseType: 'blob',
      timeout: 120000,  // proxied from GitHub Release, allow up to 2 min
    }),
  downloadInstallerBat: (storeId, name = 'Агент') =>
    api.get('/agent/installer.bat', {
      params: { store_id: storeId, name },
      responseType: 'blob',
      timeout: 30000,
    }),
}

export const exportsAPI = {
  formats: () => api.get('/exports/formats'),
  list: (params) => api.get('/exports', { params }),
  create: (formatId, storeId, productIds = null) =>
    api.post(`/exports/${formatId}`, {
      store_id: storeId,
      ...(productIds ? { product_ids: productIds } : {}),
    }),
  remove: (fileId) => api.delete(`/exports/${fileId}`),
  /** Direct URL for <a download> — token passed as query-param because
   *  browsers can't set Authorization on navigation. */
  downloadUrl: (fileId) => {
    const t = localStorage.getItem('access_token') || ''
    return `${BASE_URL}/exports/${fileId}/download?token=${encodeURIComponent(t)}`
  },
  /** URL for EventSource connection — same token-in-query trick. */
  streamUrl: () => {
    const t = localStorage.getItem('access_token') || ''
    return `${BASE_URL}/exports/stream?token=${encodeURIComponent(t)}`
  },
}

export const subscriptionsAPI = {
  status: () => api.get('/subscriptions/status'),
  createPayment: () => api.post('/subscriptions/create-payment'),
  toggleAutoRenew: () => api.post('/subscriptions/toggle-auto-renew'),
  referral: () => api.get('/subscriptions/referral'),
  applyReferral: (code) =>
    api.post('/subscriptions/apply-referral', null, { params: { code } }),
}

export default api
