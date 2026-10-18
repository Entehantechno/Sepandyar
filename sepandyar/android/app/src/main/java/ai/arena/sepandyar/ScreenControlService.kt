package ai.arena.sepandyar

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityNodeInfo

class ScreenControlService : AccessibilityService() {
    companion object {
        var instance: ScreenControlService? = null
        var pendingAction: ScreenAction? = null
    }

    private val main = Handler(Looper.getMainLooper())

    override fun onServiceConnected() { super.onServiceConnected(); instance = this }
    override fun onDestroy() { instance = null; super.onDestroy() }
    override fun onAccessibilityEvent(event: android.view.accessibility.AccessibilityEvent?) { }
    override fun onInterrupt() { }

    fun executePendingAction() {
        main.postDelayed({
            val action = pendingAction ?: return@postDelayed
            pendingAction = null
            when (action.type) {
                "tap_text" -> smartTap(action.payload, 0)
                "input_text" -> smartInput(action.payload)
                "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
                "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
                "tap_xy" -> action.payload.split(',').mapNotNull { it.trim().toFloatOrNull() }
                    .takeIf { it.size == 2 }?.let { tap(it[0], it[1]) }
            }
        }, 450)
    }

    private fun smartTap(query: String, attempt: Int): Boolean {
        val target = SmartSelector.find(rootInActiveWindow, query)
        if (target?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true) return true
        if (attempt < 8) main.postDelayed({ smartTap(query, attempt + 1) }, 350)
        return false
    }

    private fun smartInput(value: String): Boolean {
        val target = findEditable(rootInActiveWindow) ?: return false
        val args = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value) }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findAndInput(root: AccessibilityNodeInfo?, value: String): Boolean {
        if (root == null) return false
        val target = findEditable(root) ?: return false
        val args = Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value) }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable && node.isVisibleToUser) return node
        for (i in 0 until node.childCount) node.getChild(i)?.let { findEditable(it)?.also { found -> return found } }
        return null
    }

    private fun tap(x: Float, y: Float) {
        val path = Path().apply { moveTo(x, y) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 80)
        dispatchGesture(GestureDescription.Builder().addStroke(stroke).build(), null, null)
    }
}
