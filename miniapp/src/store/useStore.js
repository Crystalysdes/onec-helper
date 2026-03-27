import { create } from 'zustand'
import { updateApiToken } from '../services/api'

const useStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token') || null,
  currentStore: null,
  stores: [],
  isLoading: false,

  setUser: (user) => set({ user }),
  setToken: (token) => {
    updateApiToken(token)
    set({ token })
  },
  setCurrentStore: (store) => {
    if (store) localStorage.setItem('current_store_id', store.id)
    set({ currentStore: store })
  },
  setStores: (stores) => set({ stores }),
  setLoading: (isLoading) => set({ isLoading }),

  logout: () => {
    updateApiToken(null)
    localStorage.removeItem('current_store_id')
    set({ user: null, token: null, currentStore: null, stores: [] })
  },

  isAdmin: () => get().user?.is_admin === true,
}))

export default useStore
