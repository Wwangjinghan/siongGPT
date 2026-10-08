export interface Role {
  code: string;
  name: string;
}

export interface Department {
  id: string;
  code: string;
  name: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  status: string;
  department: Department | null;
  roles: Role[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  message: string;
  user: User;
}

export interface LogoutResponse {
  message: string;
}
