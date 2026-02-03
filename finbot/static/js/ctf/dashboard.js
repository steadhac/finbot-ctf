/**
 * FinBot CTF Dashboard
 */

// Category color mapping
const CATEGORY_COLORS = {
    'prompt_injection': 'cyan',
    'prompt-injection': 'cyan',
    'data_exfiltration': 'purple',
    'data-exfiltration': 'purple',
    'privilege_escalation': 'green',
    'privilege-escalation': 'green',
    'denial_of_service': 'yellow',
    'denial-of-service': 'yellow',
};

// Challenge category icons
const CATEGORY_ICONS = {
    'prompt_injection': '💉',
    'prompt-injection': '💉',
    'data_exfiltration': '📤',
    'data-exfiltration': '📤',
    'privilege_escalation': '🔓',
    'privilege-escalation': '🔓',
    'denial_of_service': '💥',
    'denial-of-service': '💥',
};

// Activity event icons
const EVENT_ICONS = {
    'agent': { icon: '🤖', class: 'agent' },
    'tool': { icon: '🔧', class: 'tool' },
    'business': { icon: '✅', class: 'success' },
    'llm': { icon: '💡', class: 'llm' },
    'challenge': { icon: '🎯', class: 'challenge' },
    'badge': { icon: '🏆', class: 'badge' },
};

// Badge rarity icons
const RARITY_ICONS = {
    'common': '⭐',
    'rare': '💎',
    'epic': '🌟',
    'legendary': '👑',
};

document.addEventListener('DOMContentLoaded', function () {
    loadDashboardData();
});

/**
 * Load all dashboard data in parallel
 */
async function loadDashboardData() {
    try {
        const [stats, challenges, badges, activity] = await Promise.all([
            fetchStats(),
            fetchChallenges(),
            fetchBadges(),
            fetchActivity(),
        ]);

        renderStats(stats);
        renderActiveChallenges(challenges);
        renderRecentBadges(badges);
        renderActivityFeed(activity);
        renderCategoryProgress(stats.category_progress);

    } catch (error) {
        console.error('Failed to load dashboard data:', error);
    }
}

/**
 * Fetch user stats
 */
async function fetchStats() {
    const response = await fetch('/ctf/api/v1/stats');
    if (!response.ok) throw new Error('Failed to fetch stats');
    return response.json();
}

/**
 * Fetch challenges
 */
async function fetchChallenges() {
    const response = await fetch('/ctf/api/v1/challenges');
    if (!response.ok) throw new Error('Failed to fetch challenges');
    return response.json();
}

/**
 * Fetch badges
 */
async function fetchBadges() {
    const response = await fetch('/ctf/api/v1/badges');
    if (!response.ok) throw new Error('Failed to fetch badges');
    return response.json();
}

/**
 * Fetch activity
 */
async function fetchActivity() {
    const response = await fetch('/ctf/api/v1/activity?page_size=5');
    if (!response.ok) throw new Error('Failed to fetch activity');
    return response.json();
}

/**
 * Render stats cards
 */
function renderStats(stats) {
    // Update sidebar points
    const sidebarPoints = document.getElementById('sidebar-points');
    if (sidebarPoints) {
        sidebarPoints.textContent = `${stats.total_points.toLocaleString()} pts`;
    }

    // Progress ring
    const progressPercent = stats.challenges_total > 0
        ? Math.round((stats.challenges_completed / stats.challenges_total) * 100)
        : 0;

    document.getElementById('progress-percent').textContent = `${progressPercent}%`;
    document.getElementById('challenges-completed').textContent = stats.challenges_completed;
    document.getElementById('challenges-total').textContent = stats.challenges_total;

    // Animate progress ring
    const circle = document.getElementById('progress-circle');
    const circumference = 2 * Math.PI * 35; // radius = 35
    const offset = circumference - (progressPercent / 100) * circumference;
    circle.style.strokeDasharray = circumference;
    circle.style.strokeDashoffset = offset;

    // Points
    document.getElementById('total-points').textContent = stats.total_points.toLocaleString();
    if (stats.hints_cost > 0) {
        document.getElementById('hints-cost').textContent = `-${stats.hints_cost} from hints`;
        document.getElementById('hints-cost').classList.add('text-ctf-warning');
    }

    // Badges
    document.getElementById('badges-earned').textContent = stats.badges_earned;
    document.getElementById('badges-total').textContent = stats.badges_total;

    // Hints
    document.getElementById('hints-used').textContent = stats.hints_used;
    if (stats.hints_cost > 0) {
        document.getElementById('hints-cost-display').textContent = `-${stats.hints_cost} pts`;
    }
}

/**
 * Render active challenges
 */
function renderActiveChallenges(challenges) {
    const container = document.getElementById('active-challenges');

    // Filter to show in-progress first, then available, limit to 4
    const active = challenges
        .filter(c => c.status !== 'completed')
        .sort((a, b) => {
            if (a.status === 'in_progress' && b.status !== 'in_progress') return -1;
            if (b.status === 'in_progress' && a.status !== 'in_progress') return 1;
            return 0;
        })
        .slice(0, 4);

    if (active.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8">
                <div class="text-4xl mb-3">🎉</div>
                <p class="text-text-secondary text-sm">All challenges completed!</p>
            </div>
        `;
        return;
    }

    container.innerHTML = active.map(challenge => {
        const icon = CATEGORY_ICONS[challenge.category] || '🎯';
        const iconClass = getCategoryIconClass(challenge.category);

        return `
            <a href="/ctf/challenges/${challenge.id}" class="challenge-mini">
                <div class="challenge-icon ${iconClass}">
                    ${icon}
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                        <span class="font-semibold text-text-bright truncate">${escapeHtml(challenge.title)}</span>
                        <span class="diff-${challenge.difficulty}">${challenge.difficulty}</span>
                    </div>
                    <div class="text-sm text-text-secondary truncate">${formatCategoryName(challenge.category)}</div>
                </div>
                <div class="text-right flex-shrink-0">
                    <div class="text-lg font-bold text-ctf-primary font-mono">${challenge.points} pts</div>
                    ${challenge.attempts !== undefined ? `<div class="text-xs text-text-secondary">${challenge.attempts} attempts</div>` : ''}
                </div>
            </a>
        `;
    }).join('');
}

/**
 * Render recent badges
 */
function renderRecentBadges(badges) {
    const container = document.getElementById('recent-badges');
    const noBadges = document.getElementById('no-badges');

    // Filter earned badges and sort by earned_at
    const earnedBadges = badges
        .filter(b => b.earned)
        .sort((a, b) => new Date(b.earned_at) - new Date(a.earned_at))
        .slice(0, 3);

    if (earnedBadges.length === 0) {
        container.classList.add('hidden');
        noBadges.classList.remove('hidden');
        return;
    }

    noBadges.classList.add('hidden');
    container.classList.remove('hidden');

    container.innerHTML = earnedBadges.map((badge, index) => {
        const rarityClass = `badge-rarity-${badge.rarity}`;
        const isRecent = index === 0;

        return `
            <div class="badge-item ${rarityClass} ${isRecent ? 'earned' : ''}">
                <div class="badge-icon">${badge.icon_url || RARITY_ICONS[badge.rarity] || '🏆'}</div>
                <div class="flex-1 min-w-0">
                    <div class="font-semibold text-text-bright truncate">${escapeHtml(badge.title)}</div>
                    <div class="text-xs text-text-secondary truncate">${escapeHtml(badge.description)}</div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Render activity feed
 */
function renderActivityFeed(activityResponse) {
    const container = document.getElementById('activity-feed');
    const noActivity = document.getElementById('no-activity');
    const items = activityResponse.items || [];

    if (items.length === 0) {
        container.classList.add('hidden');
        noActivity.classList.remove('hidden');
        return;
    }

    noActivity.classList.add('hidden');
    container.classList.remove('hidden');

    container.innerHTML = items.map(item => {
        const eventConfig = EVENT_ICONS[item.event_category] || EVENT_ICONS['tool'];
        const timeAgo = getTimeAgo(item.timestamp);

        return `
            <div class="activity-item">
                <div class="activity-icon ${eventConfig.class}">
                    ${eventConfig.icon}
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-medium text-text-bright">${formatEventType(item.event_type)}</span>
                        ${item.agent_name ? `<span class="activity-tag bg-purple-500/20 text-purple-300">${escapeHtml(item.agent_name)}</span>` : ''}
                        ${item.tool_name ? `<span class="activity-tag bg-cyan-500/20 text-cyan-300 font-mono text-xs">${escapeHtml(item.tool_name)}</span>` : ''}
                    </div>
                    <div class="text-sm text-text-secondary mt-1 truncate">${escapeHtml(item.summary)}</div>
                </div>
                <div class="text-xs text-text-secondary font-mono flex-shrink-0">${timeAgo}</div>
            </div>
        `;
    }).join('');
}

/**
 * Render category progress
 */
function renderCategoryProgress(categories) {
    const container = document.getElementById('category-progress');
    const noCategories = document.getElementById('no-categories');

    if (!categories || categories.length === 0) {
        container.classList.add('hidden');
        noCategories.classList.remove('hidden');
        return;
    }

    noCategories.classList.add('hidden');
    container.classList.remove('hidden');

    container.innerHTML = categories.map(cat => {
        const colorClass = CATEGORY_COLORS[cat.category] || 'cyan';

        return `
            <div class="category-progress">
                <div class="flex justify-between text-sm mb-2">
                    <span class="text-text-primary">${formatCategoryName(cat.category)}</span>
                    <span class="font-mono text-${colorClass === 'cyan' ? 'ctf-primary' : colorClass === 'purple' ? 'ctf-secondary' : colorClass === 'green' ? 'ctf-accent' : 'ctf-warning'}">${cat.completed}/${cat.total}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${colorClass}" style="width: ${cat.percentage}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Get category icon class
 */
function getCategoryIconClass(category) {
    const mapping = {
        'prompt_injection': 'injection',
        'prompt-injection': 'injection',
        'data_exfiltration': 'exfiltration',
        'data-exfiltration': 'exfiltration',
        'privilege_escalation': 'escalation',
        'privilege-escalation': 'escalation',
        'denial_of_service': 'dos',
        'denial-of-service': 'dos',
    };
    return mapping[category] || 'injection';
}

/**
 * Format category name for display
 */
function formatCategoryName(category) {
    return category
        .replace(/[-_]/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Format event type for display
 */
function formatEventType(eventType) {
    return eventType
        .replace(/[-_]/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Get human-readable time ago string
 */
function getTimeAgo(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
