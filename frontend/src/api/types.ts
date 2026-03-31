export interface ApiResp<T> {
  code: number;
  msg: string;
  data: T;
}

export interface ApiPageResp<T> {
  code: number;
  msg: string;
  data: T[];
  total: number;
}

export interface UserResp {
  id: string;
  account: string;
  email?: string | null;
  name?: string | null;
  phone?: string | null;
  department?: string | null;
  roles?: Array<{
    id: string;
    code: string;
    name: string;
  }>;
  create_time: number;
  update_time: number;
}

export interface UserLoginResp {
  access_token: string;
  token_type: string;
  user: UserResp;
}

export interface UserGroupResp {
  id: string;
  code: string;
  name: string;
  create_time: number;
  update_time: number;
}

export interface RoleResp {
  id: string;
  code: string;
  name: string;
  permissions: string[];
  create_time: number;
  update_time: number;
}
