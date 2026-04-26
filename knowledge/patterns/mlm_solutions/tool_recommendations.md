# Tool Development Recommendations

> Based on comprehensive research of LifeVantage products, compensation plan, and success strategies

## Priority 1: Content Generation Tools

### 1.1 `generate_social_post`
**Purpose**: Create compliant social media content
**Input**: Topic, platform, avatar type
**Output**: Ready-to-post content with hashtags
**Why**: 80% of success strategies center on consistent content

### 1.2 `generate_video_script`
**Purpose**: Create short-form video scripts
**Templates Needed**:
- Hook scripts (7-15 seconds)
- Bridge page scripts
- Objection handling scripts
**Why**: Video is the #1 conversion driver

### 1.3 `content_repurposer`
**Purpose**: Take pillar content, output week of posts
**Flow**: 1 video → blog + 10 shorts + carousels
**Why**: The "Content Machine" workflow is proven

---

## Priority 2: Lead Management Tools

### 2.1 `score_prospect`
**Purpose**: Analyze engagement and assign lead score
**Factors**: Content interaction, avatar fit, time in funnel
**Output**: Score (1-100) + recommended action

### 2.2 `generate_followup`
**Purpose**: Create personalized follow-up messages
**Input**: Lead data, stage in funnel, last interaction
**Output**: Personalized DM/email
**Why**: Follow-up is where 90% drop the ball

### 2.3 `track_pipeline`
**Purpose**: Manage lead stages and reminders
**Stages**: New → Engaged → Nurturing → Presented → Customer/Consultant
**Why**: DMO requires systematic follow-up

---

## Priority 3: Nurture Sequence Tools

### 3.1 `generate_email_sequence`
**Purpose**: Create full nurture sequences
**Templates**: Product-focused, opportunity-focused, hybrid
**Why**: Existing `email_nurture_sequence.md` template is proven

### 3.2 `send_nurture_message`
**Purpose**: Automated drip campaign management
**Integration**: Email provider APIs
**Why**: Consistency without manual effort

---

## Priority 4: Product Knowledge Tools

### 4.1 `explain_product`
**Purpose**: Generate compliant product explanations
**Input**: Product name, audience avatar, format
**Output**: Explanation + compliance disclaimer
**Why**: Most fail because they can't explain the science simply

### 4.2 `compare_products`
**Purpose**: Help prospects choose right products
**Input**: Goals, budget, health concerns
**Output**: Recommended stack + reasoning

### 4.3 `calculate_savings`
**Purpose**: Show value vs alternatives
**Compare**: LifeVantage vs competitor costs, coffee habit, etc.

---

## Priority 5: Business Opportunity Tools

### 5.1 `explain_compensation`
**Purpose**: Break down Evolve plan for prospects
**Modes**: Quick overview, detailed breakdown, specific rank focus
**Why**: Confusion kills signups

### 5.2 `calculate_earnings`
**Purpose**: Project potential earnings
**Input**: Time commitment, network size goals
**Output**: Estimated earnings by rank

### 5.3 `generate_onboarding`
**Purpose**: Create Fast Track checklist for new recruits
**Output**: 7-day action plan with scripts

---

## Tool Implementation Order

| Phase | Tools | Impact |
|-------|-------|--------|
| 1 | `generate_social_post`, `generate_video_script` | Content consistency |
| 2 | `score_prospect`, `generate_followup` | Lead conversion |
| 3 | `explain_product`, `compare_products` | Sales enablement |
| 4 | `generate_email_sequence` | Automation |
| 5 | `explain_compensation`, `calculate_earnings` | Recruiting |

---

## Integration Requirements

- **LLM**: Gemini for content generation
- **Compliance**: Built-in FDA disclaimer injection
- **Templates**: Load from `brain/concepts/` for consistency
- **Memory**: Track what content/messages have been sent

> [!IMPORTANT]
> All tools must include compliance layer to prevent FDA/MLM violations
