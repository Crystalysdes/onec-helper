import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 65000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
    }
    return Promise.reject(error)
  }
)

export const authAPI = {
  telegramAuth: (initData) =>
    api.post('/auth/telegram', { init_data: initData }),
  getMe: () => api.get('/auth/me'),
}

export const storesAPI = {
  list: () => api.get('/stores/'),
  create: (data) => api.post('/stores/', data),
  get: (id) => api.get(`/stores/${id}`),
  update: (id, data) => api.put(`/stores/${id}`, data),
  delete: (id) => api.delete(`/stores/${id}`),
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
    }),
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
  subscriptions: (page) => api.get('/admin/subscriptions', { params: { page } }),
  getUserSubscription: (userId) => api.get(`/admin/subscriptions/${userId}`),
  grantSubscription: (userId, days = 30) =>
    api.post(`/admin/subscriptions/${userId}/grant`, { days }),
  revokeSubscription: (userId) => api.delete(`/admin/subscriptions/${userId}`),
  backfillCatalog: () => api.post('/admin/backfill-catalog'),
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
