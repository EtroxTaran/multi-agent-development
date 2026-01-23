# Writing Effective Product Specs

The quality of the output depends entirely on the quality of your input.
In Conductor, the **`PRODUCT.md`** file is your primary interface.

---

## 📝 The Template

Every `PRODUCT.md` needs these 4 sections:

### 1. Summary
A 1-2 sentence pitch. What are we building?
> "A user profile page that allows uploading an avatar."

### 2. Acceptance Criteria (The Checklist)
This is what the agents use to write tests. **Be specific.**
*   ❌ Bad: "User can upload image."
*   ✅ Good: "User can upload a PNG/JPG up to 5MB. It is resized to 200x200px."

### 3. Usage Examples
Show, don't just tell. Providing a JSON snippet or a code example helps the agents immensely.
```json
// Example User Object
{
  "id": "123",
  "avatar_url": "https://cdn.example.com/u/123.jpg"
}
```

### 4. Technical Constraints
Set the boundaries.
*   "Must use AWS S3"
*   "Must use `shadcn/ui` components"
*   "Do not add new npm packages without asking"

---

## 🚫 Common Pitfalls

### The "Magic" Trap
Don't assume the agents know your business logic.
*   *Bad*: "Calculate the bonus."
*   *Good*: "Calculate bonus as 10% of salary if tenure > 1 year."

### Ambiguity
Words like "Fast", "Pretty", or "Secure" are meaningless to an LLM without context.
*   *Fast* -> "Response under 200ms"
*   *Pretty* -> "Use the existing Theme Provider colors"
*   *Secure* -> "Use Helmet.js headers"

---

## 🔄 Iterating
You don't have to get it perfect the first time.
1. Write a draft `PRODUCT.md`.
2. Run `./scripts/init.sh run`.
3. If the **Planning Phase** asks questions, update the `PRODUCT.md` with the answers and run it again!
