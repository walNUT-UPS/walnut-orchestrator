/**
 * Authentication service for walNUT frontend
 * Handles login, logout, and user management with cookie-based JWT auth
 */

export interface User {
  email: string;
  // Add other user properties as needed
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthError {
  message: string;
  code?: string;
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
   * Get current user information
   * This can be used to check if user is authenticated
   * Since we don't have a /me endpoint yet, we'll try to access a protected endpoint
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      // Try to access a protected endpoint to check auth status
      const response = await fetch(`/api/system/health`, {
        method: 'GET',
        credentials: 'include', // Include cookies
      });

      if (response.status === 401) {
        return null; // Not authenticated
      }

      if (!response.ok) {
        return null; // Assume not authenticated if we can't access protected resources
      }

      // If we can access protected endpoints, assume authentication is valid
      // Return a basic user object (we'll enhance this when we have a proper /me endpoint)
      return { email: 'admin@test.com' };
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
}

export const authService = new AuthService();