package ai.arena.sepandyar

import android.text.TextUtils
import android.view.accessibility.AccessibilityNodeInfo
import java.util.Locale

/**
 * پیدا کردن هوشمند عنصر بدون نیاز به selector دستی.
 * اول از semantics خود Android استفاده می‌کند و سپس با امتیازدهی متن، توضیح، hint، شناسه و شباهت واژه‌ای جلو می‌رود.
 */
object SmartSelector {
    data class Hit(val node: AccessibilityNodeInfo, val score: Int)

    fun find(root: AccessibilityNodeInfo?, query: String): AccessibilityNodeInfo? {
        if (root == null || query.isBlank()) return null
        val q = normalize(query)
        val hits = mutableListOf<Hit>()
        walk(root, q, hits)
        val best = hits.maxByOrNull { it.score } ?: return null
        if (best.score < 35) return null
        return clickableAncestor(best.node)
    }

    private fun walk(node: AccessibilityNodeInfo, q: String, hits: MutableList<Hit>) {
        if (node.isVisibleToUser) {
            val text = normalize(node.text?.toString())
            val desc = normalize(node.contentDescription?.toString())
            val hint = normalize(node.hintText?.toString())
            val id = normalize(node.viewIdResourceName?.substringAfterLast('/') ?: "")
            val score = score(q, text, desc, hint, id, node.isClickable, node.isEnabled)
            if (score > 0) hits += Hit(node, score)
        }
        for (i in 0 until node.childCount) node.getChild(i)?.let { walk(it, q, hits) }
    }

    private fun score(q: String, text: String, desc: String, hint: String, id: String, clickable: Boolean, enabled: Boolean): Int {
        if (!enabled) return 0
        val fields = listOf(text to 70, desc to 65, hint to 45, id to 30)
        var best = 0
        for ((field, weight) in fields) if (field.isNotBlank()) {
            val s = when {
                field == q -> weight + 30
                field.contains(q) || q.contains(field) -> weight
                tokens(field).intersect(tokens(q)).isNotEmpty() -> weight - 15
                levenshtein(field, q) <= 3 -> weight - 20
                else -> 0
            }
            best = maxOf(best, s)
        }
        if (clickable && best > 0) best += 20
        return best
    }

    private fun clickableAncestor(node: AccessibilityNodeInfo): AccessibilityNodeInfo {
        var current: AccessibilityNodeInfo? = node
        while (current != null) {
            if (current.isClickable && current.isEnabled) return current
            current = current.parent
        }
        return node
    }

    fun normalize(value: String?): String = (value ?: "").lowercase(Locale.ROOT)
        .replace('ي', 'ی').replace('ك', 'ک').replace('ۀ', 'ه')
        .replace(Regex("[ًٌٍَُِّْ]"), "")
        .replace(Regex("[^\\p{L}\\p{N} ]"), " ")
        .replace(Regex("\\s+"), " ").trim()

    private fun tokens(s: String) = s.split(' ').filter { it.length > 1 }.toSet()

    private fun levenshtein(a: String, b: String): Int {
        if (a == b) return 0
        val dp = IntArray(b.length + 1) { it }
        for (i in a.indices) {
            var prev = dp[0]; dp[0] = i + 1
            for (j in b.indices) {
                val temp = dp[j + 1]
                dp[j + 1] = minOf(dp[j + 1] + 1, dp[j] + 1, prev + if (a[i] == b[j]) 0 else 1)
                prev = temp
            }
        }
        return dp[b.length]
    }
}
