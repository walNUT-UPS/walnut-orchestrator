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

    let response: Response;
    try {
      response = await fetch(`/auth/jwt/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        credentials: 'include', // Include cookies
        body: formData,
      });
    } catch (_) {
      // Network or CORS failure
      throw new Error('Unable to connect to backend');
    }

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('Invalid email or password');
      }
      if (response.status >= 500) {
        throw new Error('Server error, please try again later');
      }
      const msg = await response.text().catch(() => '');
      throw new Error(msg || 'Login failed');
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
   */
  async getCurrentUser(): Promise<User | null> {
    try {
      // Use the proper /api/me endpoint to check auth status
      const response = await fetch(`/api/me`, {
        method: 'GET',
        credentials: 'include', // Include cookies
      });

      if (response.status === 401 || response.status === 403) {
        return null; // Not authenticated
      }

      if (!response.ok) {
        return null; // Not authenticated or other error
      }

      // Parse the user data from the response
      const userData = await response.json();
      return { email: userData.email || 'user@example.com' };
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
