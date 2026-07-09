import axios from 'axios';

const api = axios.create({
  baseURL: '',
  timeout: 60000 // 60s timeout for heavier RAG actions
});

// Request Interceptor: Attach JWT token if stored
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Handle auth failures globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Check if not login/register routes to avoid logging out in the middle of login
      const url = error.config.url || '';
      if (!url.includes('/api/auth/login') && !url.includes('/api/auth/register')) {
        console.warn('Authentication token expired. Clearing session.');
        localStorage.removeItem('token');
        // Force reload page to redirect to login via AuthContext status check
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

