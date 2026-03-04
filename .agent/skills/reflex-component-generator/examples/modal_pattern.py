"""
Example: Modal Dialog Pattern for Reflex

This pattern demonstrates:
1. State-managed visibility
2. Form inputs with validation
3. Async submission with loading state
4. Proper cleanup on close
"""
import reflex as rx
from typing import Optional

class ExampleModalState(rx.State):
    """State for the example modal."""
    
    # Modal visibility
    is_open: bool = False
    
    # Form fields
    name: str = ""
    description: str = ""
    
    # Loading/error state
    is_loading: bool = False
    error_message: Optional[str] = None
    
    def open_modal(self):
        """Open the modal and reset form."""
        self.name = ""
        self.description = ""
        self.error_message = None
        self.is_open = True
    
    def close_modal(self):
        """Close and cleanup."""
        self.is_open = False
        self.is_loading = False
    
    @rx.var
    def can_submit(self) -> bool:
        """Validate form before submission."""
        return len(self.name.strip()) >= 3
    
    async def submit(self):
        """Handle form submission."""
        if not self.can_submit:
            self.error_message = "Name must be at least 3 characters"
            return
        
        self.is_loading = True
        self.error_message = None
        yield  # Update UI to show loading
        
        try:
            # Perform async operation
            # await some_api_call(self.name, self.description)
            
            self.close_modal()
            # Optionally trigger refresh of parent data
            # yield AppState.load_items
            
        except Exception as e:
            self.error_message = str(e)
            self.is_loading = False


def example_modal() -> rx.Component:
    """Render the modal dialog."""
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon("plus", size=16),
                "Create New",
                variant="solid",
            )
        ),
        rx.dialog.content(
            rx.dialog.title("Create Item"),
            rx.vstack(
                # Name input
                rx.vstack(
                    rx.text("Name", size="2", weight="medium"),
                    rx.input(
                        placeholder="Enter name...",
                        value=ExampleModalState.name,
                        on_change=ExampleModalState.set_name,
                        width="100%",
                    ),
                    width="100%",
                    spacing="1",
                ),
                
                # Description input
                rx.vstack(
                    rx.text("Description", size="2", weight="medium"),
                    rx.text_area(
                        placeholder="Optional description...",
                        value=ExampleModalState.description,
                        on_change=ExampleModalState.set_description,
                        rows="3",  # Note: string, not int
                        width="100%",
                    ),
                    width="100%",
                    spacing="1",
                ),
                
                # Error display
                rx.cond(
                    ExampleModalState.error_message,
                    rx.callout(
                        ExampleModalState.error_message,
                        icon="alert-circle",
                        color="red",
                        size="1",
                    ),
                ),
                
                # Action buttons
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="soft",
                            color="gray",
                        )
                    ),
                    rx.button(
                        rx.cond(
                            ExampleModalState.is_loading,
                            rx.spinner(size="1"),
                            rx.text("Create"),
                        ),
                        disabled=~ExampleModalState.can_submit | ExampleModalState.is_loading,
                        on_click=ExampleModalState.submit,
                    ),
                    justify="end",
                    width="100%",
                ),
                
                spacing="4",
                width="100%",
            ),
            style={"max_width": "450px"},
        ),
        open=ExampleModalState.is_open,
        on_open_change=lambda open: (
            ExampleModalState.open_modal() if open 
            else ExampleModalState.close_modal()
        ),
    )
