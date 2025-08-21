/**
 * Authentication service for walNUT frontend
 * Handles login, logout, and user management with cookie-based JWT auth
 */

export interface User {
  email: string;
  role: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthError {
  message: string;
  code?: string;
}

export interface FrontendSettings {
  oidc_enabled: boolean;
  oidc_provider_name: string;
}

class AuthService {
  private baseUrl = ''; // Use root path since auth is mounted at /auth directly

  /**
   * Login user with email and password
   * Backend expects application/x-www-form-urlencoded format
   */
  async login(credentials: LoginCredentials): Promise<void> {
    const formData = new URLSearchParams();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);

    const response = await fetch(`/auth/jwt/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      credentials: 'include', // Include cookies
      body: formData,
    });

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Invalid email or password');
      } else if (response.status >= 500) {
        throw new Error('Server error, please try again later');
      } else {
        throw new Error('Connection failed, please try again');
      }
    }

    // Backend returns HTTP 204 No Content on successful login
    // The JWT token is set as a cookie automatically
  }

  /**
   * Logout user and clear authentication
   */
  async logout(): Promise<void> {
    try {
      const response = await fetch(`/auth/jwt/logout`, {
        method: 'POST',
        credentials: 'include', // Include cookies
      });

      if (!response.ok) {
        console.warn('Logout request failed, but proceeding with local cleanup');
      }
    } catch (error) {
      console.warn('Logout request failed, but proceeding with local cleanup:', error);
    }

    // Clear any local auth state if needed
    // The backend should clear the cookie
  }

  /**
   * Get current user information by calling the /api/me endpoint.
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      const response = await fetch(`/api/me`, {
        method: 'GET',
        credentials: 'include', // Include cookies
      });

      if (response.status === 401) {
        return null; // Not authenticated
      }

      if (!response.ok) {
        return null; // Assume not authenticated if we can't access protected resources
      }

      const user = await response.json();
      return user;
    } catch (error) {
      console.error('Error checking authentication:', error);
      return null;
    }
  }

  /**
   * Check if user is authenticated by attempting to fetch user info
   */
  async isAuthenticated(): Promise<boolean> {
    const user = await this.getCurrentUser();
    return user !== null;
  }

  async getFrontendSettings(): Promise<FrontendSettings> {
    try {
      const response = await fetch(`/api/settings/frontend`);
      if (!response.ok) {
        throw new Error("Failed to fetch frontend settings");
      }
      return await response.json();
    } catch (error) {
      console.error("Error fetching frontend settings:", error);
      // Return default settings if the endpoint fails
      return {
        oidc_enabled: false,
        oidc_provider_name: "",
      };
    }
  }
}

export const authService = new AuthService();