
import axios, { type AxiosRequestConfig } from "axios";

const api = axios.create({
  baseURL:
    import.meta.env.VITE_API_BASE_URL ??
    "http://localhost:8000/api/v1",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

const apiService = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    api.get<T>(url, config),

  post: <T, D = unknown>(
    url: string,
    data?: D,
    config?: AxiosRequestConfig
  ) => api.post<T>(url, data, config),

  put: <T, D = unknown>(
    url: string,
    data?: D,
    config?: AxiosRequestConfig
  ) => api.put<T>(url, data, config),

  patch: <T, D = unknown>(
    url: string,
    data?: D,
    config?: AxiosRequestConfig
  ) => api.patch<T>(url, data, config),

  delete: <T = void>(
    url: string,
    config?: AxiosRequestConfig
  ) => api.delete<T>(url, config),
};

export default apiService;
