# Pattern: Self-Annealing

## Definition
The **Self-Annealing Pattern** is a system improvement loop where errors are treated as learning opportunities that strengthen the system over time.

## The Loop
1. **Error Occurs** → Something breaks or produces unexpected results
2. **Fix It** → Debug and resolve the immediate issue
3. **Update the Tool** → Modify execution scripts to handle the edge case
4. **Test Tool** → Verify the fix works correctly
5. **Update Directive** → Document the learning in the relevant directive
6. **System Stronger** → Future runs benefit from the improvement

## Examples

### API Rate Limit
> Error: API returned 429 Too Many Requests
> Fix: Add exponential backoff retry logic
> Update: Document rate limits in directive

### Missing Data
> Error: KeyError when parsing customer without email
> Fix: Add default values and Optional typing
> Update: Add "Edge Cases" section to directive

### File Permission
> Error: PermissionError writing to logs
> Fix: Use `os.makedirs(exist_ok=True)` and handle IOError
> Update: Add file system permissions note

## Key Principles
- **Don't just fix; improve** - Every error is a chance to make the system more robust
- **Document everything** - Future agents (and humans) need to know what was learned
- **Test after fixing** - Avoid breaking other things in the process
- **Preserve knowledge** - Directives are living documents

## Related Tags
`Reliability`, `Error Handling`, `Continuous Improvement`, `Documentation`
