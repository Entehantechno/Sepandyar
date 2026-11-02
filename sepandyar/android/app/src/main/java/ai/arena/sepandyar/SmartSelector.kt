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

    /**
     * یکسان‌سازی متن فارسی برای تطبیق.
     *
     * چهار اختلاف نویسه‌ای که در اپ‌های فارسی **واقعاً** دیده می‌شوند و بدون این
     * یکسان‌سازی تطبیق را می‌شکنند:
     *
     *  1. **نیم‌فاصله (U+200C)** — «می‌رود» و «میرود» یک چیزند. نسخهٔ پیشین
     *     نیم‌فاصله را با قاعدهٔ «هرچه نویسه نیست، فاصله» به فاصله تبدیل
     *     می‌کرد، پس این دو **هرگز** به هم نمی‌رسیدند.
     *  2. **رقم عربی (U+0660..0669) در برابر فارسی (U+06F0..06F9) و لاتین** —
     *     هر سه «۱۲۳» هستند. هر سه `\p{N}`‌اند، پس نسخهٔ پیشین هیچ‌کدام را
     *     به دیگری نزدیک نمی‌کرد.
     *  3. **تطویل/کشیده (U+0640)** — «تأیــید» و «تأیید» یک چیزند؛ تطویل در
     *     ردهٔ `\p{L}` است پس نسخهٔ پیشین نگهش می‌داشت.
     *  4. **الف و واو با همزهٔ عربی** — «تأييد» و «تایید» یک چیزند.
     *
     *  5. **دو شکل نشانگر اضافه** — «حملهٔ» (ه + U+0654) و «حملهۀ» (U+06C0)
     *     یک چیزند، پس U+06C0 حذف می‌شود و U+0654 با بقیهٔ اعراب می‌رود.
     *
     * `آ` (U+0622) و `ئ` (U+0626) عمداً دست‌نخورده می‌مانند: در فارسی نویسه‌های
     * مستقل‌اند («آب» در برابر «اب») و یکسان‌سازی‌شان تطبیق کاذب می‌سازد.
     */
    fun normalize(value: String?): String {
        if (value.isNullOrEmpty()) return ""
        val sb = StringBuilder(value.length)
        for (ch in value.lowercase(Locale.ROOT)) {
            when (ch) {
                '\u200C', '\u200D', '\u0640' -> { /* حذف: نیم‌فاصله و تطویل نامرئی‌اند */ }
                '\u064A' -> sb.append('\u06CC')              // ي عربی ← ی فارسی
                '\u0643' -> sb.append('\u06A9')              // ك عربی ← ک فارسی
                '\u06C0' -> { /* حذف: در فارسی تنها نشانگر اضافه است */ }
                '\u0629' -> sb.append('\u0647')              // ة ← ه
                '\u0623', '\u0625' -> sb.append('\u0627')   // أ إ ← ا
                '\u0624' -> sb.append('\u0648')              // ؤ ← و
                in '\u0660'..'\u0669' -> sb.append('0' + (ch - '\u0660'))  // رقم عربی ← لاتین
                in '\u06F0'..'\u06F9' -> sb.append('0' + (ch - '\u06F0'))  // رقم فارسی ← لاتین
                else -> sb.append(ch)
            }
        }
        return sb.toString()
            .replace(Regex("[\u064B-\u065F\u0670\u06D6-\u06ED]"), "")
            .replace(Regex("[^\\p{L}\\p{N} ]"), " ")
            .replace(Regex("\\s+"), " ").trim()
    }

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
