import { config } from '../config'
import type { ApiErrorBody } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Field-level validation messages flattened to "field: message" strings. */
  get fieldErrors(): string[] {
    if (this.code !== 'validation_error') return []
    const lines: string[] = []
    const walk = (value: unknown, path: string) => {
      if (Array.isArray(value) && value.every((v) => typeof v === 'string')) {
        lines.push(`${path}: ${value.join(' ')}`)
      } else if (value && typeof value === 'object') {
        for (const [key, inner] of Object.entries(value)) walk(inner, path ? `${path}.${key}` : key)
      }
    }
    walk(this.details, '')
    return lines
  }
}

function isErrorBody(body: unknown): body is ApiErrorBody {
  return typeof body === 'object' && body !== null && 'error' in body
}

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init
  let response: Response
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...rest,
      headers: {
        Accept: 'application/json',
        ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection.')
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (isErrorBody(body)) {
      const { code, message, details } = body.error
      throw new ApiError(response.status, code, message, details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed (${response.status}).`)
  }
  return body as T
}
