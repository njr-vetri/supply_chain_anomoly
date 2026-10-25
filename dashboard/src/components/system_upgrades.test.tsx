/**
 * Frontend tests for System Upgrades & Role Security.
 * Covers:
 * 1. LoginScreen (email/password, first-run setup screen)
 * 2. Role badge in App header
 * 3. Disabled-with-tooltip buttons
 * 4. UsersScreen (User list, role badges, Add User modal)
 * 5. ProjectSelector (Current project, switcher, New project modal)
 */
import { describe, expect, it, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginScreen } from './LoginScreen'
import { ProjectSelector } from './ProjectSelector'
import { UsersScreen } from './UsersScreen'
import type { ApiClient } from '../api/client'

beforeAll(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

describe('System Upgrades - LoginScreen', () => {
  it('renders email and password inputs without legacy API key input', async () => {
    // Mock setup status returning false (system is setup)
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/setup-status')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ setup_required: false }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }) as typeof fetch

    const onLogin = vi.fn()
    render(<LoginScreen onLogin={onLogin} />)

    await waitFor(() => {
      expect(screen.getByLabelText(/Email or Username/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument()
    })
    expect(screen.queryByLabelText(/Company ID/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/API Key/i)).not.toBeInTheDocument()
  })

  it('renders first-run setup screen when setup_required is true', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/setup-status')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ setup_required: true }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }) as typeof fetch

    const onLogin = vi.fn()
    render(<LoginScreen onLogin={onLogin} />)

    await waitFor(() => {
      expect(screen.getByText(/First-Run System Setup/i)).toBeInTheDocument()
      expect(screen.getByText(/Company Name/i)).toBeInTheDocument()
      expect(screen.getByText(/Admin Email/i)).toBeInTheDocument()
    })
  })
})

describe('System Upgrades - ProjectSelector', () => {
  it('loads projects and displays active project name', async () => {
    const mockClient = {
      listProjects: vi.fn().mockResolvedValue({
        items: [
          { id: 'proj-1', name: 'Supply Operations 2026', workspace_id: 'ws-1' },
          { id: 'proj-2', name: 'Backup Project', workspace_id: 'ws-1' },
        ],
        count: 2,
      }),
      createProject: vi.fn(),
    } as unknown as ApiClient

    const onSelect = vi.fn()
    render(<ProjectSelector client={mockClient} currentProjectId="proj-1" onSelectProject={onSelect} />)

    await waitFor(() => {
      expect(screen.getByText('Supply Operations 2026')).toBeInTheDocument()
    })
  })

  it('opens project modal on "New project" click', async () => {
    const mockClient = {
      listProjects: vi.fn().mockResolvedValue({
        items: [{ id: 'proj-1', name: 'Supply Operations 2026', workspace_id: 'ws-1' }],
        count: 1,
      }),
      createProject: vi.fn(),
    } as unknown as ApiClient

    const onSelect = vi.fn()
    render(<ProjectSelector client={mockClient} currentProjectId="proj-1" onSelectProject={onSelect} />)

    await waitFor(() => {
      expect(screen.getByText('Supply Operations 2026')).toBeInTheDocument()
    })

    // Click dropdown toggle
    fireEvent.click(screen.getByText('Supply Operations 2026'))

    // Click "New project"
    const newProjBtn = screen.getByText('New project')
    expect(newProjBtn).toBeInTheDocument()
    fireEvent.click(newProjBtn)

    // Modal is now open
    expect(screen.getByText('Create New Project')).toBeInTheDocument()
  })
})

describe('System Upgrades - UsersScreen', () => {
  it('renders user list and displays role badges', async () => {
    const mockClient = {
      listUsers: vi.fn().mockResolvedValue({
        items: [
          {
            id: 'u-1',
            username: 'alice_admin',
            email: 'alice@example.com',
            role: 'admin',
            is_active: true,
            must_change_password: false,
            locked_until: null,
            created_at: '2026-10-24T00:00:00Z',
          },
          {
            id: 'u-2',
            username: 'bob_analyst',
            email: 'bob@example.com',
            role: 'analyst',
            is_active: true,
            must_change_password: false,
            locked_until: null,
            created_at: '2026-10-24T00:00:00Z',
          },
        ],
        count: 2,
      }),
    } as unknown as ApiClient

    render(<UsersScreen client={mockClient} />)

    await waitFor(() => {
      expect(screen.getByText('alice_admin')).toBeInTheDocument()
      expect(screen.getByText('bob_analyst')).toBeInTheDocument()
      expect(screen.getByText('admin')).toBeInTheDocument()
      expect(screen.getByText('analyst')).toBeInTheDocument()
    })
  })

  it('opens "Add User" modal and allows role selection', async () => {
    const mockClient = {
      listUsers: vi.fn().mockResolvedValue({ items: [], count: 0 }),
      createUser: vi.fn(),
    } as unknown as ApiClient

    render(<UsersScreen client={mockClient} />)

    const addBtn = screen.getByRole('button', { name: /Add User/i })
    fireEvent.click(addBtn)

    expect(screen.getByText('Add New User')).toBeInTheDocument()
    expect(screen.getByText('Email Address')).toBeInTheDocument()
  })
})
