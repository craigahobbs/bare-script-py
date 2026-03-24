# BareScript Tips

Here are a few tips for generating BareScript code:

1. Multi-line BareScript statements require the use of the line-continuation character, `\\`.
   Function definitions, for loops, while loops, and if-else conditionals are not considered
   multi-line statements and so do not require the line-continuation character. For example:

   ```barescript
   function myAppFunction():
       items = { \\
           'A': 1, \\
           'B': 2 \\
       }
       for item in objectKeys(items):
           markdownPrint('', '- ' + item)
       endfor
   endfunction
   ```

2. The `windowClipboardWrite` function is `async` and any function that calls it must be `async` as
   well. For example:

   ```barescript
   async function myAppCopyText(text):
       windowClipboardWrite(text)
   endfunction
   ```

3. There are no inline function definitions (e.g. `fn = lambda x: x + 1`). in BareScript. All functions
   must be defined in the global scope. For example:

   ```barescript
   function myIncrement(x):
       return x + 1
   endfunction
   ```

4. There is no `await` keyword in BareScript - it is implicit when calling `async` functions.

5. Please use common BareScript best practices:

   - Use lower-case, camel-case for variables and function names
   - Prefix your globals with your application prefix (e.g. `myAppCategories`)
   - Define your main entry point in a "main" function (e.g. `myAppMain`)

   For example:

   ```barescript
   function myAppMain():
       # Render the title
       title = 'Hello, World!'
       documentSetTitle(title)
       markdownPrint('# ' + markdownEscape(title))

       # Render the names
       for name in myAppNames:
           markdownPrint('', 'Hello, ' + name + '!')
       endfor
   endfunction

   # The names to say "hello" to
   myAppNames = [ \\
       'World', \\
       'Pussy Cat' \\
   ]

   myAppMain()
   ```

6. Always follow the BareScript common blank line rules:

   - ensure function definitions and global statement groups are separated by two blank lines

   - within functions, ensure code statement groups are separated by a single blank line

   - within conditional blocks, ensure code statement groups are separated by a single blank line


7. Always follow the BareScript common commenting rules:

   - ensure function definitions and global statement groups are adequately commented

   - within functions, ensure code statement groups are adequately commented

   - within conditional blocks, ensure code statement groups are adequately commented

8. When porting from a different language (e.g. JavaScript), port the code as directly as possible.
   The code should be as identical as possible. Don't add or remove code unless its absolutely
   necessary. Please give notes on any issues you run into. If the source language raises
   exceptions, do a `systemLogDebug` and return null.
