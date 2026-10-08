"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { routes } from "@/lib/routes";
import { ApiError } from "@/lib/api";
import { login } from "@/lib/auth";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { MicrosoftIcon } from "./MicrosoftIcon";

export function LoginCard() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [ssoNotice, setSsoNotice] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    setError(null);
    setSsoNotice(false);
    setIsLoading(true);

    try {
      await login({ email, password });
      await refreshUser();
      router.push(routes.gpt);
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof ApiError
          ? submitError.message
          : "Unable to sign in. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="card-shadow flex w-full max-w-[730px] items-center rounded-[18px] border border-line bg-white px-8 py-6 sm:px-12 lg:min-h-[590px] lg:px-[68px]">
      <div className="mx-auto w-full max-w-[592px]">
        <header className="mb-5 text-center">
          <h1 className="text-[34px] font-extrabold leading-tight tracking-[-.03em]">Welcome back</h1>
          <p className="mt-1 text-[18px] text-muted-blue">Sign in to access Siong GPT</p>
        </header>

        <form onSubmit={handleSubmit} noValidate={false}>
          <div className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-[15px] font-semibold">Email address</label>
              <div className="relative">
                <Mail aria-hidden className="absolute left-5 top-1/2 -translate-y-1/2 text-[#8190ac]" size={24} />
                <Input id="email" name="email" type="email" autoComplete="email" required placeholder="name@Siong.com" value={email} onChange={(event) => setEmail(event.target.value)} disabled={isLoading} className="h-[52px] pl-[58px] text-[16px]" />
              </div>
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-[15px] font-semibold">Password</label>
              <div className="relative">
                <LockKeyhole aria-hidden className="absolute left-5 top-1/2 -translate-y-1/2 text-[#8190ac]" size={24} />
                <Input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required minLength={1} placeholder="Enter your password" value={password} onChange={(event) => setPassword(event.target.value)} disabled={isLoading} className="h-[52px] px-[58px] text-[16px]" />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} className="focus-ring absolute right-4 top-1/2 -translate-y-1/2 rounded-md p-2 text-[#8190ac] hover:text-brand-navy" aria-label={showPassword ? "Hide password" : "Show password"}>
                  {showPassword ? <EyeOff size={24} /> : <Eye size={24} />}
                </button>
              </div>
            </div>
          </div>

          {error ? <p role="alert" className="mt-2 text-[12px] text-red-600">{error}</p> : null}

          <div className="my-4 flex items-center">
            <Checkbox id="remember" className="size-6" checked={rememberMe} disabled={isLoading} onCheckedChange={(checked) => setRememberMe(checked === true)} />
            <label htmlFor="remember" className="ml-3 cursor-pointer text-[15px]">Remember me</label>
            <button type="button" className="focus-ring ml-auto rounded-md px-1 py-1 text-[15px] font-medium text-action hover:underline">Forgot password?</button>
          </div>

          <Button type="submit" disabled={isLoading} className="h-[52px] w-full rounded-[9px] text-[17px]">
            {isLoading ? "Signing in..." : <>Sign in <ArrowRight size={22} /></>}
          </Button>

          <div className="my-4 flex items-center gap-5 text-[13px] text-muted-blue"><span className="h-px flex-1 bg-line" /><span>OR</span><span className="h-px flex-1 bg-line" /></div>

          <Button type="button" variant="outline" onClick={() => setSsoNotice(true)} className="h-[52px] w-full rounded-[9px] text-[17px] font-semibold">
            <span className="scale-90"><MicrosoftIcon /></span> Sign in with Microsoft
          </Button>
          {ssoNotice ? <p role="status" className="mt-3 text-center text-sm text-brand-green">Microsoft SSO will be connected later</p> : null}
        </form>

        <footer className="mt-5 text-center text-muted-blue">
          <p className="flex items-center justify-center gap-2.5 text-[13px]"><ShieldCheck size={20} /> For authorized Siong employees only</p>
          <p className="mt-1.5 text-[11px]">By signing in, you agree to our IT policies and acceptable use guidelines.</p>
        </footer>
      </div>
    </section>
  );
}
