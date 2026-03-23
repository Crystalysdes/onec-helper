import { create } from 'zustand'

const useStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token') || null,
  currentStore: null,
  stores: [],
  isLoading: false,

  setUser: (user) => set({ user }),
  setToken: (token) => {
    localStorage.setItem('access_token', token)
    set({ token })
  },
  setCurrentStore: (store) => {
    if (store) localStorage.setItem('current_store_id', store.id)
    set({ currentStore: store })
  },
  setStores: (stores) => set({ stores }),
  setLoading: (isLoading) => set({ isLoading }),

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_store_id')
    set({ user: null, token: null, currentStore: null, stores: [] })
  },

  isAdmin: () => get().user?.is_admin === true,
}))

export default useStore
