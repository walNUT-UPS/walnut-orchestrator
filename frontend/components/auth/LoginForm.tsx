import React, { useState } from 'react';
import { Card } from '../ui/card';
import { Eye, EyeOff, Shield, AlertCircle, LogIn } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { toast } from 'sonner';

interface LoginFormProps {
  onSuccess?: () => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [stage, setStage] = useState<'email' | 'password'>('email');
  const [oidcEnabled, setOidcEnabled] = useState<boolean>(false);

  const onLogin = async (username: string, password: string) => {
    try {
      setIsLoading(true);
      setError(null);
      await login(username, password);
      toast.success('Welcome to walNUT');
      onSuccess?.();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (stage === 'email') {
      // Allow any email to proceed; validate after password
      if (username.trim()) {
        setStage('password');
      }
      return;
    }
    if (stage === 'password' && username.trim() && password.trim()) {
      onLogin(username.trim(), password);
    }
  };

  const isEmailValid = !!username.trim();
  const isFormValid = stage === 'email' ? isEmailValid : (username.trim() && password.trim());

  const beginOidcLogin = () => {
    // Prefer explicit backend URL if provided; fall back to common dev default :8000
    const backendBase = (import.meta as any).env?.VITE_BACKEND_URL
      || `${location.protocol}//${location.hostname}:8000`;
    const authorize = `${backendBase}/auth/oauth/oidc/authorize`;
    const redirect = `${backendBase}/auth/oauth/oidc/callback`;
    const params = new URLSearchParams();
    params.set('scopes', 'openid email profile');
    params.set('redirect_url', redirect);
    window.location.href = `${authorize}?${params.toString()}`;
  };

  React.useEffect(() => {
    // Detect if backend has OIDC enabled via settings; hide button otherwise
    (async () => {
      try {
        const cfg = await fetch('/api/system/oidc/config', { credentials: 'include' }).then(r => r.ok ? r.json() : null);
        setOidcEnabled(!!cfg?.enabled);
      } catch (_) {
        setOidcEnabled(false);
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex items-center justify-center p-6">
      <div className="w-full max-w-md mx-auto">
        <Card className="bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm border border-gray-200/50 dark:border-gray-700/50 shadow-2xl rounded-2xl p-8">
          <div className="space-y-6">
            {/* Header */}
            <div className="text-center space-y-3">
              <div className="mx-auto w-16 h-16 bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl flex items-center justify-center mb-6 shadow-lg">
                <Shield className="w-8 h-8 text-white" />
              </div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
                walNUT
              </h1>
              <p className="text-base text-gray-600 dark:text-gray-400 font-medium">
                UPS Orchestration Platform
              </p>
            </div>

            <div className="border-t border-gray-200 dark:border-gray-700"></div>

            {/* Error Alert */}
            {error && (
              <div className="bg-red-50/80 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-xl p-4 backdrop-blur-sm">
                <div className="flex items-start">
                  <AlertCircle className="h-5 w-5 text-red-500 dark:text-red-400 mt-0.5 flex-shrink-0" />
                  <div className="ml-3 text-sm text-red-700 dark:text-red-300 font-medium">{error}</div>
                </div>
              </div>
            )}

            {/* Login Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Step 1: Email */}
              <div className="space-y-3">
                <label htmlFor="username" className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                  Email
                </label>
                <input
                  id="username"
                  type="email"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="you@example.com"
                  disabled={isLoading || stage === 'password'}
                  className="w-full h-12 px-4 py-3 border-2 border-gray-200 dark:border-gray-600 rounded-xl bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 disabled:opacity-60 shadow-sm"
                  autoComplete="username"
                  autoFocus
                />
              </div>

              {/* Step 2: Password (only after email) */}
              {stage === 'password' && (
                <div className="space-y-3">
                  <label htmlFor="password" className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      disabled={isLoading}
                      className="w-full h-12 px-4 py-3 pr-12 border-2 border-gray-200 dark:border-gray-600 rounded-xl bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200 disabled:opacity-50 shadow-sm"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors duration-200 p-1"
                      disabled={isLoading}
                    >
                      {showPassword ? (
                        <EyeOff className="w-5 h-5" />
                      ) : (
                        <Eye className="w-5 h-5" />
                      )}
                    </button>
                  </div>
                </div>
              )}

              {/* Submit / Continue */}
              <div className="pt-2 space-y-3">
                <button
                  type="submit"
                  className="w-full h-12 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 disabled:from-blue-300 disabled:to-blue-400 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl transform hover:scale-[1.02] active:scale-[0.98]"
                  disabled={!isFormValid || isLoading}
                >
                  {isLoading ? 'Signing in...' : stage === 'email' ? 'Continue' : 'Sign In'}
                </button>
                {stage === 'password' && (
                  <button
                    type="button"
                    className="w-full h-10 text-sm font-medium rounded-xl border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                    onClick={() => setStage('email')}
                    disabled={isLoading}
                  >
                    Back
                  </button>
                )}
              </div>
            </form>

            {oidcEnabled && (
              <>
                {/* OR Divider */}
                <div className="flex items-center gap-3 my-2">
                  <div className="h-px bg-gray-200 dark:bg-gray-700 flex-1" />
                  <span className="text-xs text-gray-500 dark:text-gray-400">OR</span>
                  <div className="h-px bg-gray-200 dark:bg-gray-700 flex-1" />
                </div>

                {/* OIDC Button */}
                <button
                  type="button"
                  onClick={beginOidcLogin}
                  className="w-full h-11 inline-flex items-center justify-center gap-2 rounded-xl border border-gray-300 dark:border-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 font-semibold transition-colors"
                  disabled={isLoading}
                >
                  <LogIn className="w-4 h-4" />
                  Login with OIDC
                </button>
              </>
            )}

            <div className="border-t border-gray-200/50 dark:border-gray-700/50"></div>

            {/* Footer */}
            <div className="text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">
                Secure access to UPS monitoring and orchestration
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
